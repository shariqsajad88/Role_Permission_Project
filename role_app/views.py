from django.contrib.auth.models import Group, Permission, User 
from googleapiclient.discovery import build
from google.oauth2 import service_account
from django.conf import settings
from django.http import JsonResponse
from django.views import View
import logging
from .models import RolePermission
from django.views.generic import TemplateView
from django.db.models import Count
logger = logging.getLogger(__name__)


class ExportRolesPermissionsView(View):
    def get(self, request, *args, **kwargs):
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        SERVICE_ACCOUNT_FILE = settings.GOOGLE_CREDENTIALS_JSON

        try:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Service account file error: {str(e)}")
            return JsonResponse({"status": "Error", "message": str(e)}, status=500)

        SAMPLE_SPREADSHEET_ID = getattr(settings, 'SHEET_ID', None)
        if not SAMPLE_SPREADSHEET_ID:
            logger.error("SHEET_ID not configured in settings")
            return JsonResponse({"status": "Error", "message": "SHEET_ID not configured in settings."}, status=500)

        # Initialize Google Sheets service
        try:
            sheet_service = build('sheets', 'v4', credentials=creds)
            sheet = sheet_service.spreadsheets()
        except Exception as e:
            logger.error(f"Error initializing Google Sheets service: {str(e)}")
            return JsonResponse({"status": "Error", "message": "Failed to initialize Google Sheets service."}, status=500)

        # Fetch all permissions
        all_permissions = Permission.objects.all()

        # Fetch RolePermission data
        role_permissions = RolePermission.objects.select_related("user", "role").prefetch_related("role__permissions").all()

        # Build header row
        header = ["Username", "Role"] + [f"{perm.content_type.app_label}.{perm.codename}" for perm in all_permissions]
        data = [header]

        # Append data rows
        for rp in role_permissions:
            # Create a dictionary of permissions with default "N"
            permission_dict = {f"{perm.content_type.app_label}.{perm.codename}": "N" for perm in all_permissions}

            # Mark granted permissions as "Y"
            for perm in rp.role.permissions.all():
                perm_key = f"{perm.content_type.app_label}.{perm.codename}"
                if perm_key in permission_dict and rp.granted:
                    permission_dict[perm_key] = "Y"

            # Build row with permission statuses
            row = [rp.user.username, rp.role.name if rp.role else "No Role"] + list(permission_dict.values())
            data.append(row)

        try:
            sheet_metadata = sheet.get(spreadsheetId=SAMPLE_SPREADSHEET_ID).execute()
            sheets = sheet_metadata.get('sheets', '')
            sheet_names = [s['properties']['title'] for s in sheets]

            roles_permissions_sheet_id = None

            # Create 'RolesPermissions' sheet if it doesn't exist
            if 'RolesPermissions' not in sheet_names:
                request_body = {
                    'requests': [{
                        'addSheet': {
                            'properties': {'title': 'RolesPermissions'}
                        }
                    }]
                }
                response = sheet.batchUpdate(
                    spreadsheetId=SAMPLE_SPREADSHEET_ID,
                    body=request_body
                ).execute()
                roles_permissions_sheet_id = response['replies'][0]['addSheet']['properties']['sheetId']
                logger.info("Created 'RolesPermissions' sheet")

            # Append data to Google Sheets
            result = sheet.values().update(
                spreadsheetId=SAMPLE_SPREADSHEET_ID,
                range="RolesPermissions",
                valueInputOption="RAW",
                body={"values": data}
            ).execute()

            # Apply formatting to header row if new sheet was created
            if roles_permissions_sheet_id is not None:
                format_requests = [{
                    'repeatCell': {
                        'range': {
                            'sheetId': roles_permissions_sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8},
                                'textFormat': {'bold': True}
                            }
                        },
                        'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                    }
                }]
                sheet.batchUpdate(
                    spreadsheetId=SAMPLE_SPREADSHEET_ID,
                    body={'requests': format_requests}
                ).execute()

            logger.info(f"Sheet update result: {result}")
        except Exception as e:
            logger.error(f"Error exporting to Google Sheets: {str(e)}")
            return JsonResponse({"status": "Error", "message": f"Failed to export roles to Google Sheets: {str(e)}"}, status=500)

        return JsonResponse({"status": "Success", "message": "Roles and permissions exported to Google Sheets."})






class AdminDashboardView(TemplateView):
    template_name = 'admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistics
        context['user_count'] = User.objects.count()
        context['group_count'] = Group.objects.count()
        context['permission_count'] = Permission.objects.count()

        # Role distribution stats
        role_distribution = Group.objects.annotate(user_count=Count('user'))
        context['role_distribution'] = [(role.name, role.user_count) for role in role_distribution]

        # Recent permission changes (assuming RolePermission tracks changes)
        recent_changes = RolePermission.objects.order_by('-updated_at')[:5]
        context['recent_changes'] = recent_changes

        return context
    


