"""商店系统（world-v1.4.11 起）：导播账本 / 进货订单 / 餐厅菜单。"""
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

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


@router.get("/shop/menu")
def get_menu(shop: str = "restaurant"):
    """v1.4.13：餐厅菜单（与 objects[bar].menu 同）。"""
    if shop != "restaurant":
        raise HTTPException(status_code=404, detail=f"no menu for {shop}")
    with world_state.STATE_LOCK:
        return {"shop": "restaurant", "menu": shops.menu_view(world_state._players, world_state._OBJECTS, world_state.game_now_ts()),
                "orders": shops.kitchen_orders_view()}


@router.get("/admin/passersby")
def get_passersby():
    """v1.4.14：路人日程与在场状态（导播 / 冒烟用）。"""
    from game import passerby
    with world_state.STATE_LOCK:
        return passerby.view()


class StockEdit(BaseModel):
    object: str = "counter"
    item: str
    qty: int
    reason: Optional[str] = None


@router.post("/admin/shop/stock")
def admin_set_stock(body: StockEdit, authorization: Optional[str] = Header(default=None)):
    """v1.4.12：主镇用的库存直写（总控 / 主播决定的数据修正；scenario 在主镇是 403）。鉴权同 /school/term_start；记 interventions data_edit 与账本。"""
    toks = [t for t in (os.environ.get("SANDBOX_ADMIN_TOKEN"), os.environ.get("SELF_TOKEN")) if t]
    if toks and (authorization or "") not in {f"Bearer {t}" for t in toks}:
        raise HTTPException(status_code=401, detail="bad token")
    from game import inventory, interventions
    with world_state.STATE_LOCK:
        obj = world_state.get_object_by_id(body.object)
        if obj is None or (obj.get("stock") is None and obj.get("contents") is None):
            raise HTTPException(status_code=404, detail=f"no shop stock / storage on {body.object}")
        if inventory.item_def(body.item) is None:
            raise HTTPException(status_code=400, detail=f"unknown item {body.item}")
        after = max(0, int(body.qty))
        if obj.get("contents") is not None:                          # v1.4.17：冰箱（逐条内容，带保质期）——补进 / 拿出到目标数
            from game import food
            before = sum(int(c.get("count", 0)) for c in obj["contents"] if c["item"] == body.item and not c.get("meta"))
            if after > before:
                food.store(obj, body.item, after - before, inventory.expires_at_for(body.item, world_state.game_now_ts()))
            elif after < before:
                food.take(obj, body.item, before - after)
            after = sum(int(c.get("count", 0)) for c in obj["contents"] if c["item"] == body.item and not c.get("meta"))
        else:
            before = int(obj["stock"].get(body.item, 0))
            obj["stock"][body.item] = after
        world_state.refresh_shop_views()
        shop_key = shops.shop_of_object(obj["id"]) or ("restaurant" if obj["id"] in shops.cfg()["restaurant"]["kitchen_fridges"] else None)
        shops.record(shop_key, "adjust", who="system", item=body.item, qty=after - before, amount=0,
                     note=f"库存直写 {before} → {after}" + (f"（{body.reason}）" if body.reason else ""))
        interventions.log("data_edit", "system", [obj["id"]], f"{obj['name']}库存 {body.item} {before} → {after}" + (f"：{body.reason}" if body.reason else ""),
                          payload={"object": obj["id"], "item": body.item, "before": before, "after": after}, reversible=True)
        return {"ok": True, "object": obj["id"], "item": body.item, "before": before, "after": after, "stock": dict(obj.get("stock") or {})}
