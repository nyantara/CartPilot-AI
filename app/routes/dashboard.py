from fastapi import APIRouter, HTTPException, status
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=DashboardSummaryResponse, status_code=status.HTTP_200_OK)
def get_dashboard_summary():
    """
    Retrieve real-time merchant operations overview:
    order counts, payment statuses, total gross sales, recent orders, and stock alerts.
    """
    try:
        summary = DashboardService.get_dashboard_summary()
        return DashboardSummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate dashboard summary: {str(e)}"
        )

