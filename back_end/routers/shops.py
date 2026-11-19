"""商店系统（world-v1.4.11 起）：导播账本 / 进货订单 / 餐厅菜单。"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from game import shops, world_state

router = APIRouter(tags=["shops"])


@router.get("/shops/{shop_id}/ledger")
def get_ledger(shop_id: str, days: int = 7):
    """导播视角：三本账都能看（shop_id = 物件 id counter / bar / fish_stall，或账本名 grocery / restaurant / fish_stall）。不做权限、不写动作日志。"""
    shop = shop_id if shop_id in shops.cfg()["ledgers"] else shops.shop_of_object(shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail=f"no ledger for {shop_id}")
    with world_state.STATE_LOCK:
        return shops.ledger_view(shop, days)


@router.get("/shop/orders")
def get_orders(shop: Optional[str] = None, status: Optional[str] = None):
    with world_state.STATE_LOCK:
        return {"orders": shops.orders_view(shop, status)}
