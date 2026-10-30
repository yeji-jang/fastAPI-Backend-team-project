"""
<예매 endpoint 정보>

- 예매 생성 : POST /v1/reservations
- 예매 목록 조회 : GET /v1/reservations
- 예매 상세 조회 : GET /v1/reservations/{reserv_id}
- 예매 취 : POST /v1/reservations/{reserv_id}/cancel
"""

# 라우터 작업 초기세팅
from fastapi import APIRouter, HTTPException, status, Path, Header, Body, Depends

router = APIRouter(prefix="/v1/reservations", tags=["예매"])


# 엔드포인트(endpoint) 정의
@router.post("", 
            summary="예매 생성", 
            description="로그인한 회원이 좌석 1개를 선택해 결제를 마치면 예매가 확정")
async def create_reservation(
):
    pass

@router.get("", 
            summary="예매 목록 조회", 
            description="로그인한 회원이 본인의 예매 내역을 최신순으로 확인 취소한 예매 포함")
async def get_list_reservation(
):
    pass

@router.get("/{reserv_id}", 
            summary="예매 상세 조회", 
            description="로그인한 회원이 본인의 예매 1건을 공연·좌석·결제 정보까지 자세히 확인")
async def get_detail_reservation(
    reserv_id: int = Path(description="예매번호")
):
    pass

@router.post("/{reserv_id}/cancel", 
            summary="예매 취소", 
            description="로그인한 회원이 본인의 확정된 예매를 취소하면 결제 금액이 환불되고 좌석이 다시 판매 가능")
async def cancel_reservation(
    reserv_id: int = Path(description="예매번호")
):
    pass


