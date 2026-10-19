# define deployment behaviour based on supplied app spec
def deploy() -> None:
    from smart_contracts.artifacts.hello_world.hello_world_client import (
        HelloArgs,
        HelloWorldFactory,
    )

    algorand = algokit_utils.AlgorandClient.from_environment()
    deployer = algorand.account.from_environment("DEPLOYER")

    factory = algorand.client.get_typed_app_factory(
        HelloWorldFactory,
        default_sender=deployer.address,
    )

    app_client, result = factory.deploy(
        on_update=algokit_utils.OnUpdate.AppendApp,
        on_schema_break=algokit_utils.OnSchemaBreak.AppendApp,
    )

    if result.operation_performed in [
        algokit_utils.OperationPerformed.Create,
        algokit_utils.OperationPerformed.Replace,
    ]:
        algorand.send_payment(
            algokit_utils.PaymentParams(
                amount=algokit_utils.AlgoAmount(algo=1),
                sender=deployer.address,
                receiver=app_client.app_address,
            )
        )

    name = "World"

    response = app_client.send.hello(
        args=HelloArgs(name=name)
    )

    logger.info(
        f"Called hello on {app_client.app_name} "
        f"({app_client.app_id}) with name={name}, "
        f"received: {response.abi_return}"
    )

