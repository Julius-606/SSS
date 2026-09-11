# Job Connection App Transformation

## Goal Description

Transform the existing "SSS Portal OS" Streamlit application from a task management system for employees into a job connection platform that links verified clients with verified service providers (formerly employees). This involves refactoring the data model, updating the user interface for new roles (Clients, Service Providers), and adapting the notification system to a job-centric workflow.

## Proposed Changes

### `app.py`

#### [MODIFY] [app.py](file:///C:/Users/lenovo/Jay/Projects/SSS/app.py)

*   **Configuration**:
    *   Rename `ADMIN_USER`, `ADMIN_PASS` for clarity.
    *   Add `CLIENT_SHEET_URL` if clients will use a separate sheet, or update `SHEET_URL` reference.
*   **Google Sheets Connection**:
    *   Modify `get_worksheets` to create/manage a "Clients" worksheet in addition to "Workers" (formerly "Employees"), "Jobs" (formerly "Tasks"), "Settings", and "Accounting".
    *   Update `emps_ws` and `tasks_ws` to `workers_ws` and `jobs_ws` respectively.
    *   Ensure initial data setup for "Workers" and "Clients" if sheets are empty.
*   **Data Pull**:
    *   Modify `fetch_portal_data` to fetch data for "Clients", "Workers", and "Jobs".
    *   Rename `emps_df` to `workers_df` and `tasks_df` to `jobs_df`.
*   **Monthly Auto-Archive Engine**:
    *   Update references from `tasks_df` to `jobs_df`.
*   **Write Functions**:
    *   Rename `save_tasks` to `save_jobs`.
    *   Rename `save_emps` to `save_workers`.
    *   Add `save_clients` function.
*   **Login Screen**:
    *   Modify authentication logic to support three roles: Admin, Worker (formerly Employee), and Client.
    *   Update UI elements for clarity (e.g., "Authorized Personnel Only" to "Authorized Users Only").
*   **Admin Dashboard**:
    *   Update navigation menu items (e.g., "Operations Dashboard" to "Job & Worker Management", "Finance & Analytics" to "Finance & Client Billing").
    *   Rename "Add New Employee" to "Add New Worker".
    *   Introduce UI for managing clients (Add, View, Edit Clients).
    *   Update "View As Employee" to "View As Worker/Client" with appropriate phasing logic.
    *   Refactor "Assign a Task" to "Post a Job".
    *   Update "Active Field Operations" to "Active Job Postings" and include job application management.
    *   Refactor "Master Task Ledger" to "Master Job Ledger".
    *   Update "Finance & Analytics" to reflect client billing and worker payroll for jobs.
*   **Employee Dashboard (to be Worker Dashboard)**:
    *   Rename all UI elements and logic from "Employee" to "Worker".
    *   Refactor "My Assigned Tasks" to "My Available Jobs" and "My Accepted Jobs".
    *   Implement job application functionality.
    *   Adjust task status flow to job application/acceptance flow.
*   **New Client Dashboard**:
    *   Implement UI for clients to post new jobs.
    *   Allow clients to view applications, select workers, and manage job status.
    *   Implement client payment and invoicing features.
*   **Helper Functions**:
    *   Rename `get_employee_name` to `get_worker_name`.
    *   Add `get_client_name`.

### `WA_notify.py`

#### [MODIFY] [WA_notify.py](file:///C:/Users/lenovo/Jay/Projects/SSS/WA_notify.py)

*   **Configuration**:
    *   Update `SHEET_URL` if necessary.
*   **Google Sheets Connection**:
    *   Modify to connect to "Workers" (formerly "Employees"), "Jobs" (formerly "Tasks"), and "Clients" worksheets.
*   **Data Pull**:
    *   Update `tasks_df` to `jobs_df` and `emps_df` to `workers_df`.
*   **Notification Triggers**:
    *   Refactor existing notification logic for job assignments, reminders, and late alerts to be job-centric.
    *   Implement new notifications for job applications, client job postings, and worker selections.
    *   Adjust messages to include job titles, worker names, and client names.
*   **Variable Renaming**: Update all instances of `emp_`, `task_` to `worker_`, `job_`, `client_` etc., as appropriate.

## Verification Plan

### Manual Verification
*   **Login**: Verify that Admin, Worker, and Client can log in successfully.
*   **Admin Dashboard**:
    *   Verify adding new workers and clients.
    *   Verify posting new jobs.
    *   Verify job application and assignment process.
    *   Verify finance and payroll functionality with the new job model.
*   **Worker Dashboard**:
    *   Verify workers can view available jobs and apply.
    *   Verify job status updates.
    *   Verify earnings and pending balances.
*   **Client Dashboard**:
    *   Verify clients can post jobs.
    *   Verify clients can view applications and select workers.
*   **WhatsApp Notifications**:
    *   Verify all new and updated notification types are sent correctly with accurate information (e.g., new job posting, job application, job confirmed, job complete).