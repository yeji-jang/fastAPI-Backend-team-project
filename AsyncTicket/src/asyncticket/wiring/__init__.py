"""도메인별 의존성 연결의 공용 진입점."""
from fastapi import FastAPI
from asyncticket.wiring.catalog_auth import wire_dependencies as wire_catalog_auth_dependencies
from asyncticket.wiring.shows import wire_dependencies as wire_show_dependencies
from asyncticket.wiring.performances import wire_dependencies as wire_performance_dependencies
from asyncticket.wiring.venues import wire_dependencies as wire_venue_dependencies
from asyncticket.wiring.payment import wire_dependencies as wire_payment_dependencies
from asyncticket.wiring.seats import wire_dependencies as wire_seat_dependencies
from asyncticket.wiring.performance_seats import wire_dependencies as wire_performance_seat_dependencies
from asyncticket.wiring.reservations import wire_dependencies as wire_reservation_dependencies


def wire_dependencies(app: FastAPI) -> None:
    wire_catalog_auth_dependencies(app)
    wire_show_dependencies(app)
    wire_performance_dependencies(app)
    wire_venue_dependencies(app)
    wire_payment_dependencies(app)
    wire_seat_dependencies(app)
    wire_performance_seat_dependencies(app)
    wire_reservation_dependencies(app)
