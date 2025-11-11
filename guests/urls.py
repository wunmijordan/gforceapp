from django.urls import path
from . import views

urlpatterns = [
    # Default page: Guest List
    path('guests/', views.guest_list_view, name='guest_list'),

    # Chart Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Guest Creation + Editing
    path('guest/create/', views.create_guest, name='create_guest'),
    path('guest/<int:pk>/edit/', views.edit_guest, name='edit_guest'),
    path("guest/<int:guest_id>/detail/", views.guest_detail_api, name="guest_detail_api"),


    # Guest detail by custom_id
    path("reviews/submit/<int:guest_id>/<str:role>/", views.submit_review, name="submit_review"),
    path('guest/<int:guest_id>/mark_read/', views.mark_reviews_read, name='mark_reviews_read'),


    # Status updates
    path('status/<int:pk>/', views.update_guest_status, name='update_guest_status'),
    path('guest/<int:guest_id>/status/<str:status_key>/', views.update_status_view, name='update_status'),
    path('guest/<int:guest_id>/reassign/', views.reassign_guest, name='reassign_guest'),
    path('bulk-delete-guests/', views.bulk_delete_guests, name='bulk_delete_guests'),


    # Import/Export
    path('export-csv/', views.export_csv, name='export_csv'),
    path("import/", views.import_guests_csv, name="import_guests_csv"),
    path("download-template/", views.download_csv_template, name="download_csv_template"),
    path('export/excel/', views.export_guests_excel, name='export_guests_excel'),
    path('import/excel/', views.import_guests_excel, name='import_excel'),
    path('export/pdf/', views.export_guests_pdf, name='export_guests_pdf'),

    # Follow-Up
    # urls.py

    path('guests/<int:guest_id>/report/', views.followup_report_page, name='followup_report_page'),
    path('<int:guest_id>/followup/', views.followup_history_view, name='followup_history'),
    path('guests/<int:guest_id>/export-pdf/', views.export_followup_reports_pdf, name='export_followup_reports_pdf'),



    # Charts & API
   
     # AJAX Endpoints
    
    path('ajax/services-attended/', views.services_attended_chart, name='services_attended_chart'),
    path('ajax/channel-breakdown/', views.channel_breakdown, name='channel_breakdown'),

    # Guest Entry Summary
    path('ajax/guest-entry-summary/', views.guest_entry_summary, name='guest_entry_summary'),

    # Top 10 Services
    path('ajax/top-services/', views.top_services_data, name='top_services_data'),

    path("attendance/", views.mark_attendance, name="mark_attendance"),
]
