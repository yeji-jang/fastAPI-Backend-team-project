"""토스 주문번호(orderId) 규칙.

- 팀 결정: orderId는 예매 번호(reserv_id)로 만든다. 예매 1건 = 결제 1건.
- 토스 규칙: 영문 대소문자·숫자·`-`·`_`, 6자 이상 64자 이하 (어기면 INVALID_ORDER_ID).
  reserv_id만으로는 6자가 안 될 수 있어 접두어를 붙인다: "<prefix>-<reserv_id>"
- 토스는 이미 승인·취소된 orderId를 다시 쓰면 DUPLICATED_ORDER_ID로 거절한다.
  팀원 로컬 DB끼리 reserv_id가 겹치므로, 같은 테스트 키를 쓰면 접두어를 사람마다 다르게 둔다.

<쓰는 곳>
    1) 결제 시작·조회 응답 : make_order_id → 프론트가 토스 결제창에 그대로 넣는다
    2) 결제 승인 요청      : parse_order_id → 토스가 돌려준 orderId에서 reserv_id를 꺼낸다
    - 접두어는 wiring/payment.py가 환경 변수 TOSS_ORDER_PREFIX(기본 "reserv")로 정한다
"""

# <표준 라이브러리>
import re # 형식 검사

# <Domain - 결제>
from asyncticket.payment.domain.exceptions import InvalidOrderIdException # 형식이 틀리면 400

# 1. 형식 규칙
_ORDER_ID = re.compile(r"^[A-Za-z0-9_-]{6,64}$")   # 토스 orderId 규칙
_PREFIX = re.compile(r"^[A-Za-z0-9_]{1,40}$")      # 접두어에는 '-'를 넣지 않는다 (마지막 '-' 뒤가 reserv_id)


# 2. 주문번호 만들기 : reserv_id → "<prefix>-<reserv_id>"
def make_order_id(prefix: str, reserv_id: int) -> str:
    # 1) 접두어 형식 확인
    if not _PREFIX.fullmatch(prefix):
        raise InvalidOrderIdException("주문번호 접두어는 영문·숫자·_만, 40자 이하로 설정해야 합니다.")
    # 2) 합친 결과가 토스 규칙(6~64자)에 맞는지 확인
    order_id = f"{prefix}-{reserv_id}"
    if not _ORDER_ID.fullmatch(order_id):
        raise InvalidOrderIdException()
    return order_id


# 3. 주문번호 해석 : "<prefix>-<reserv_id>" → reserv_id
def parse_order_id(prefix: str, order_id: str) -> int:
    """주문번호에서 reserv_id를 꺼낸다. 이 서버가 만든 형식이 아니면 거절한다."""
    # 1) 마지막 '-'를 기준으로 접두어와 번호를 나눈다
    head, sep, tail = order_id.rpartition("-")
    # 2) 접두어가 같고, 번호가 숫자이고, 토스 규칙에 맞아야 한다
    if sep != "-" or head != prefix or not tail.isdigit() or not _ORDER_ID.fullmatch(order_id):
        raise InvalidOrderIdException()
    return int(tail)
