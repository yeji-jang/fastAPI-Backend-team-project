from sqlalchemy.orm import DeclarativeBase


# 좌석 ORM 모델을 등록하는 전용 부모 클래스.
class SeatsBase(DeclarativeBase):
    pass
