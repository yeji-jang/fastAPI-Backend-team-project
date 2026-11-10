"""화면만 렌더링한다. 업무 처리는 브라우저에서 기존 /v1 API를 호출한다."""

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Path as PathParameter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
PositiveId = Annotated[int, PathParameter(gt=0, le=9223372036854775807)]


@router.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request, "Home.html")


@router.get("/login")
async def login(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/signup")
async def signup(request: Request):
    return templates.TemplateResponse(request, "signup.html")


@router.get("/me")
async def profile(request: Request):
    return templates.TemplateResponse(request, "profile.html")


@router.get("/venues")
async def venues(request: Request):
    return templates.TemplateResponse(request, "venues.html")


@router.get("/venues/{venue_id}")
async def venue(request: Request, venue_id: PositiveId):
    return templates.TemplateResponse(request, "venue.html", {"venue_id": venue_id})


@router.get("/shows")
async def shows(request: Request):
    return templates.TemplateResponse(request, "shows.html")


@router.get("/shows/{show_id}")
async def show(request: Request, show_id: PositiveId):
    return templates.TemplateResponse(request, "show.html", {"show_id": show_id})


@router.get("/performances/{performance_id}")
async def performance(request: Request, performance_id: PositiveId):
    return templates.TemplateResponse(
        request, "performance.html", {"performance_id": performance_id}
    )


@router.get("/manage/bookings")
async def manage_bookings(request: Request):
    return templates.TemplateResponse(request, "manage_bookings.html")


@router.get("/manage/edit")
async def manage_edit(request: Request):
    return templates.TemplateResponse(request, "manage.html")


@router.get("/manage")
@router.get("/manage/catalog")
async def manage(request: Request):
    return templates.TemplateResponse(request, "manage_catalog.html")


@router.get("/reservations")
async def reservations(request: Request):
    return templates.TemplateResponse(request, "reservations.html")


@router.get("/me/reservations")
async def my_reservations(request: Request):
    return templates.TemplateResponse(request, "my_reservations.html")


@router.get("/checkout/{reserv_id}")
async def checkout(request: Request, reserv_id: PositiveId):
    return templates.TemplateResponse(
        request, "checkout.html", {"reserv_id": reserv_id}
    )


@router.get("/payment/success")
async def payment_success(request: Request):
    return templates.TemplateResponse(
        request, "payment_result.html", {"result": "success"}
    )


@router.get("/payment/fail")
async def payment_fail(request: Request):
    return templates.TemplateResponse(
        request, "payment_result.html", {"result": "fail"}
    )


@router.get("/web/config", response_class=JSONResponse)
async def public_config():
    key = os.getenv("TOSS_CLIENT_KEY", "")
    # 프론트용 공개 키만 허용한다. 서버 시크릿 키는 응답에 포함하지 않는다.
    if not key.startswith(("test_ck_", "live_ck_")):
        key = ""
    return JSONResponse(
        {"toss_client_key": key or None}, headers={"Cache-Control": "no-store"}
    )
