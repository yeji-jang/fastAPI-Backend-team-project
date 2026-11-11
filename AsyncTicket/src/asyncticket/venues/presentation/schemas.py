from pydantic import BaseModel, ConfigDict, Field


class CreateVenueRequest(BaseModel):
    name: str = Field(description="공연장명")
    address: str = Field(description="주소")
    address_detail: str | None = Field(description="주소 상세")
    post_no: str = Field(description="우편번호")


class UpdateVenueRequest(BaseModel):
    venues_id: int = Field(description="공연장 ID")
    name: str = Field(description="공연장명")
    address: str = Field(description="주소")
    address_detail: str | None = Field(None, description="주소 상세")
    post_no: str | None = Field(None, description="우편번호")


class SearchVenuesRequest(BaseModel):
    name: str | None = Field(None, description="검색 공연장명")
    address: str | None = Field(None, description="검색 주소")
    page: int = Field(ge=1, description="검색 페이지")
    page_size: int = Field(ge=1, description="검색 사이즈")


class VenueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    venues_id: int
    name: str
    address: str
    address_detail: str | None
    post_no: str | None
