from fastapi import APIRouter, HTTPException, Query

from clipper.api.dependencies import discovery_service
from clipper.discovery import CountryOption, DiscoveryResult, DiscoveryUnavailableError

router = APIRouter()


@router.get("/discovery/countries", response_model=list[CountryOption])
def discovery_countries() -> tuple[CountryOption, ...]:
    return discovery_service.countries()


@router.get("/discovery", response_model=DiscoveryResult)
def discover(
    country: str = Query(default="US", min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$"),
    limit: int = Query(default=8, ge=1, le=12),
    query: str | None = Query(default=None, max_length=120),
    category: str = Query(default="trending", max_length=40),
) -> DiscoveryResult:
    try:
        return discovery_service.discover(country, limit, query=query, category=category)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DiscoveryUnavailableError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
