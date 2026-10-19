import time
import json
from flask import Flask, request, jsonify, render_template
import algokit_utils
from algosdk import account, transaction
from algosdk.transaction import PaymentTxn
from smart_contracts.artifacts.hello_world.hello_world_client import HelloWorldFactory, HelloArgs

app = Flask(__name__)

# --- GLOBAL LEDGER MEMORY ---
AURA_LEDGER = []

class AURABrain:
    """The General Purpose Oracle: Categorizes and prices any service."""
    
    @staticmethod
    def negotiate(prompt, budget):
        text = prompt.lower()
        budget_val = int(budget)
        
        # 1. CATEGORY DEFINITIONS
        categories = {
            "Development": {
                "base": 8000, 
                "keywords": ["code", "software", "app", "website", "smart contract", "python", "backend"],
                "reasoning": "High-level technical skill and infrastructure setup required."
            },
            "Hardware": {
                "base": 12000,
                "keywords": ["robot", "drone", "sensor", "titanium", "motor", "mechanical", "circuit"],
                "reasoning": "Physical component procurement and assembly complexity detected."
            },
            "Creative": {
                "base": 3000,
                "keywords": ["design", "logo", "video", "graphics", "art", "branding", "editing"],
                "reasoning": "Creative asset generation and aesthetic refinement needed."
            },
            "Consulting": {
                "base": 5000,
                "keywords": ["research", "advice", "strategy", "analysis", "marketing", "plan"],
                "reasoning": "Expert data analysis and strategic roadmap planning required."
            }
        }

        # 2. IDENTIFY CATEGORY
        detected_cat = "General Service"
        market_floor = 4000 # Default
        reason = "Standard service fee for unclassified tasks."

        for cat, data in categories.items():
            if any(key in text for key in data["keywords"]):
                detected_cat = cat
                market_floor = data["base"]
                reason = data["reasoning"]
                break

        # 3. COMPLEXITY ANALYSIS
        complexity_mult = 1.0
        if any(word in text for word in ["urgent", "complex", "professional", "custom", "advanced"]):
            complexity_mult = 1.5
            reason += " Added premium for high-complexity/priority requirements."
        elif "simple" in text or "basic" in text:
            complexity_mult = 0.7
            reason += " Discount applied for low-complexity task scope."

        final_rate = int(market_floor * complexity_mult)

        # 4. FINAL DECISION (WITH EMBEDDED PRICE)
        if budget_val >= final_rate:
            return {"status": "approved", "service": f"{detected_cat} Task", "offer": budget_val}
        else:
            return {
                "status": "counter", 
                "service": f"{detected_cat} Task", 
                "offer": final_rate,
                "message": f"AURA {detected_cat} Oracle: {reason} The calculated market floor is {final_rate:,} MicroAlgos."
            }

# --- ROUTES ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/find-service", methods=["POST"])
def find_service():
    data = request.json
    user_req = data.get("request", "")
    user_budget = data.get("budget", 0)

    ai_decision = AURABrain.negotiate(user_req, user_budget)

    if ai_decision["status"] == "counter":
        return jsonify({
            "status": "counter_offer",
            "service": ai_decision["service"],
            "counter_price": ai_decision["offer"],
            "message": ai_decision["message"]
        })

    # --- BLOCKCHAIN ESCROW ---
    try:
        algorand = algokit_utils.AlgorandClient.default_localnet()
        buyer = algorand.account.localnet_dispenser()
        
        # Generate new wallets for Seller and Platform
        _, seller_address = account.generate_account()
        _, platform_address = account.generate_account()

        # --- THE SMART SPLIT MATH ---
        budget_int = int(user_budget)
        platform_fee = int(budget_int * 0.02) # 2% AURA Fee
        seller_payout = budget_int - platform_fee # 98% to Seller
        
        # 🟢 THE FIX: Both wallets must receive the 100,000 MBR
        seller_total = seller_payout + 100000 
        platform_total = platform_fee + 100000 

        params = algorand.client.algod.suggested_params()

        # 1. Transaction A: Buyer pays the Seller (98% + MBR)
        txn_seller = PaymentTxn(
            sender=buyer.address, 
            sp=params,
            receiver=seller_address, 
            amt=seller_total
        )
        
        # 2. Transaction B: Buyer pays the AURA Platform (2% + MBR)
        txn_platform = PaymentTxn(
            sender=buyer.address, 
            sp=params,
            receiver=platform_address, 
            amt=platform_total
        )

        # --- ATOMIC TRANSFER (Grouped Smart Contract) ---
        # This guarantees both transactions happen together, or neither happen.
        transaction.assign_group_id([txn_seller, txn_platform])
        
        # Buyer signs both transactions
        signed_seller = txn_seller.sign(buyer.private_key)
        signed_platform = txn_platform.sign(buyer.private_key)

        # Send them to the blockchain simultaneously
        tx_id = algorand.client.algod.send_transactions([signed_seller, signed_platform])

        # --- RECORD TO LIVE LEDGER ---
        AURA_LEDGER.insert(0, { 
            "tx_id": tx_id,
            "service": ai_decision["service"],
            "amount": f"{budget_int:,}",
            "time": time.strftime("%H:%M:%S")
        })

        # Smart Contract Receipt
        factory = HelloWorldFactory(algorand=algorand, default_sender=buyer.address)
        client, _ = factory.deploy()
        client.send.hello(args=HelloArgs(name=ai_decision["service"]))

        return jsonify({
            "status": "success",
            "service": ai_decision["service"],
            "tx_id": tx_id,
            "buyer": buyer.address[:8],
            "seller": seller_address[:8],
            # 🟢 ADD THESE TWO LINES SO THE UI CAN SEE THE MATH:
            "seller_amount": seller_payout,
            "platform_fee": platform_fee
        })

    except Exception as e:
        return jsonify({"status": "error", "message": f"Ledger Failure: {str(e)}"}), 500

@app.route("/api/ledger")
def get_ledger():
    return jsonify(AURA_LEDGER)

if __name__ == "__main__":
    app.run(port=5001, debug=True)