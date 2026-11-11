"""
결제 서비스 주입 지점
    - 라우터는 이 함수만 Depends로 요청한다 (router.py의 Service 별칭)
    - 실제 서비스 조립은 wiring/payment.py가 app.dependency_overrides로 바꿔 끼운다
        → 요청 세션 하나로 결제 저장소·토스 호출·예매 어댑터를 만들어 꽂는다
    - wiring 연결이 빠지면 아래 예외로 바로 드러난다
"""

# <Application - 결제>
from asyncticket.payment.application.service import PaymentService # 결제 응용 서비스


# 1. 주입 지점 (기본 구현 없음)
def provider_payment_service() -> PaymentService:
    # 실제 구현은 wiring/payment.py가 dependency_overrides로 바꿔 끼운다.
    raise NotImplementedError("PaymentService 의존성이 주입되지 않았습니다.")
