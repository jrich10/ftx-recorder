import time
from datetime import datetime
import threading
import logging
import sys
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

from config import *


logger = logging.getLogger("account_recorder")


client = InfluxDBClient(
    host="localhost", port=8086, database="accountdb"
)

if drop_db:
    try:
        client.create_database("accountdb")
    except InfluxDBClientError:
        # Drop and create
        logger.info("Deleting Existing account database.")
        client.drop_database("accountdb")
        client.create_database("accountdb")
    finally:
        logger.info("Created new account database.")
else:
    try:
        client.create_database("accountdb")
    except InfluxDBClientError:
        logger.info("Using existing account database.")
        client.switch_database("accountdb")
    else:
        logger.info("Created new account database.")


def get_account():
    try:
        account = Exchange.privateGetAccount()
    except ccxt.BaseError as e:
        logger.error(f"Could not get account with error: {e}")
        return
    else:
        logger.info("Writing account.")
        t = datetime.utcnow().isoformat()
        account = account["result"]
        positions = account["positions"]

        account_write = {
            "measurement": "account",
            "tags": {
                "username": account["username"],
            },
            "fields": {
                "collateral": account["collateral"],
                "freeCollateral": account["freeCollateral"],
                "marginFraction": account["marginFraction"],
                "openMarginFraction": account["openMarginFraction"],
                "totalAccountValue": account["totalAccountValue"],
                "totalPositionSize": account["totalPositionSize"],
            },
            "time": t,
        }
        account_write["fields"] = {k: v for k, v in account_write["fields"].items() if v is not None}
        client.write_points([account_write])

        if positions:
            logger.info("Writing positions.")
            positions_write = [{
                "measurement": "positions",
                "tags": {
                    "future": p["future"],
                },
                "fields": {
                    "collateralUsed": p["collateralUsed"],
                    "cost": p["cost"],
                    "entryPrice": p["entryPrice"],
                    "estimatedLiquidationPrice": p["estimatedLiquidationPrice"],
                    "netSize": p["netSize"],
                    "openSize": p["openSize"],
                    "realizedPnl": p["realizedPnl"],
                    "side": p["side"],
                    "size": p["size"],
                    "unrealizedPnl": p["unrealizedPnl"],
                },
                "time": t,
            } for p in positions]
            for p in positions_write:
                p["fields"] = {k: v for k, v in p["fields"].items() if v is not None}
            client.write_points(positions_write)


def get_balances():
    try:
        balances = Exchange.fetchBalance()
    except ccxt.BaseError as e:
        logger.error(f"Could not get balances with error: {e}")
        return
    else:
        logger.info("Writing balances.")
        t = datetime.utcnow().isoformat()
        balances = balances["info"]["result"]

        balances_write = [{
            "measurement": "balances",
            "tags": {
                "coin": c["coin"],
            },
            "fields": {
                "free": c["free"],
                "total": c["total"],
                "usdValue": c["usdValue"],
            },
            "time": t,
        } for c in balances]
        client.write_points(balances_write)


def get_orders():
    # grab last 5 minutes worth
    since = int(time.time() - 300)
    try:
        orders = Exchange.privateGetOrdersHistory(params={'start_time': since})
    except ccxt.BaseError as e:
        logger.error(f"Could not get order history with error: {e}")
        return
    else:
        logger.info("Writing orders.")
        orders = orders["result"]

        if orders:
            orders_write = [{
                "measurement": "orders",
                "tags": {
                    "future": o["future"],
                    "market": o["market"],
                    "type": o["type"],
                    "side": o["side"],
                    "reduceOnly": o["reduceOnly"],
                    "status": o["status"],
                    "postOnly": o["postOnly"],
                    "ioc": o["ioc"]
                },
                "fields": {
                    "avgFillPrice": o["avgFillPrice"],
                    "filledSize": o["filledSize"],
                    "id": o["id"],
                    "price": o["price"],
                    "size": o["size"],
                },
                "time": o["createdAt"][:-6] + 'Z',
            } for o in orders]
            for o in orders_write:
                o["fields"] = {k: v for k, v in o["fields"].items() if v is not None}
            client.write_points(orders_write)


def get_fills():
    # grab last 5 minutes worth
    since = int(time.time() - 300)
    try:
        fills = Exchange.privateGetFills(params={'start_time': since})
    except ccxt.BaseError as e:
        logger.error(f"Could not get fills history with error: {e}")
        return
    else:
        logger.info("Writing fills.")
        fills = fills["result"]

        if fills:
            fills_write = [{
                "measurement": "fills",
                "tags": {
                    "future": f["future"],
                    "market": f["market"],
                    "type": f["type"],
                    "liquidity": f["liquidity"],
                    "side": f["side"],
                },
                "fields": {
                    "fee": f["fee"],
                    "feeRate": f["feeRate"],
                    "id": f["id"],
                    "orderId": f["orderId"],
                    "price": f["price"],
                    "size": f["size"],
                    "type": f["type"],
                },
                "time": f["time"][:-6] + 'Z',
            } for f in fills]
            for f in fills_write:
                f["fields"] = {k: v for k, v in f["fields"].items() if v is not None}
            client.write_points(fills_write)


def recorder():
    logger.info("Starting round.")
    threads = [
        threading.Thread(target=get_account),
        threading.Thread(target=get_balances),
        threading.Thread(target=get_orders),
        threading.Thread(target=get_fills),
    ]
    for thread in threads:
        thread.start()
        thread.join()


def main():
    logger.info("Starting Main.")
    while True:
        recorder()
        time.sleep(1.0)


if __name__ == "__main__":
    logger.info("Starting account recorder.")
    try:
        main()
    except ccxt.BaseError as ee:
        logger.error(f"Main ccxt error {ee}")
        sys.exit(1)
    except Exception as ee:
        logger.error(f"Main error {ee}")
        sys.exit(1)
