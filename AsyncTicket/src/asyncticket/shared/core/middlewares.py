from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp


class CorsFastAPI(FastAPI):
    # 최종 500 응답도 CORS를 거치도록 오류 처리 계층 바깥을 감싼다.
    def build_middleware_stack(self) -> ASGIApp:
        return CORSMiddleware(
            super().build_middleware_stack(),
            allow_origins=["https://asyncticket.teamsparta.xyz"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
