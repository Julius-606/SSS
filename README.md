# SSS Employment Portal

The SSS Employment Portal is a Streamlit-based business application for Swift-hands Student Services. It supports verified employers, accredited job seekers, vacancy administration, application management, financial planning, and WhatsApp notifications.

## Features

*   **Role-Based Access**: Controlled access for administrators, employers, and job seekers.
*   **Administration Dashboard**:
    *   Register and manage employer and job seeker accounts.
    *   Review verification and accreditation status.
    *   Publish and manage employment vacancies.
    *   Preview verified user dashboards for support and oversight.
*   **Employer Dashboard**:
    *   Publish vacancies with role, qualification, compensation, and deadline details.
    *   Review applications and manage shortlisting, hiring, and vacancy closure.
*   **Job Seeker Dashboard**:
    *   Browse verified employment opportunities.
    *   Submit and withdraw applications.
    *   Monitor application status.
*   **Financial Planning**: Corporate financial modelling for compensation, billing, payroll, and retained earnings.
*   **WhatsApp Notification Service**:
    *   Announces new vacancies and applications.
    *   Notifies users of shortlisting, hiring, rejection, and vacancy closure.
    *   Integrated with Meta's official WhatsApp Cloud API.

## Setup

Follow these steps to get your SSS Portal OS up and running.

### 1. Python Environment

It is recommended to use a virtual environment for Python projects.

```bash
python -m venv venv
source venv/bin/activate # On Windows: .\venv\Scripts\activate
```

### 2. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 3. Google Sheets Database Setup

This application uses Google Sheets as its primary database.

1.  **Create a Google Sheet**: Create a new Google Sheet in your Google Drive. This sheet stores employer, job seeker, vacancy, settings, and accounting data. The default URL is:
    `https://docs.google.com/spreadsheets/d/1lwK7P0Ul32suA1tOJMwrvPwawkMcVXIz5zNECVeUtfQ/edit?usp=sharing`
    You can update the `SHEET_URL` variable in `app.py` and `WA_notify.py` if you use a different sheet.

2.  **Service Account Credentials**:
    *   Go to the Google Cloud Console ([console.cloud.google.com](https://console.cloud.google.com/)).
    *   Create a new project or select an existing one.
    *   Enable the "Google Sheets API" and "Google Drive API" for your project.
    *   Create a new service account:
        *   Navigate to "IAM & Admin" > "Service Accounts."
        *   Click "+ CREATE SERVICE ACCOUNT."
        *   Provide a name and description.
        *   Grant the service account the "Editor" role on your Google Sheet.
        *   Create a new JSON key for the service account and download it.

3.  **Streamlit Secrets**:
    For the `app.py` Streamlit application, you'll need to configure your Google Sheets service account credentials as secrets. Create a `.streamlit/secrets.toml` file in your project root with the content of your downloaded JSON key. It should look like this:

    ```toml
    [gcp_service_account]
    type = "service_account"
    project_id = "your-project-id"
    private_key_id = "your-private-key-id"
    private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
    client_email = "your-service-account-email@your-project-id.iam.gserviceaccount.com"
    client_id = "your-client-id"
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account-email.iam.gserviceaccount.com"
    ```

4.  **Environment Variable for `WA_notify.py`**:
    For `WA_notify.py`, you can provide the credentials as an environment variable named `GCP_SERVICE_ACCOUNT`. The value should be the entire JSON content of your service account key, as a single-line string. You can also save the JSON content into a file and provide the path as the environment variable.

### 4. WhatsApp API Setup

The `WA_notify.py` script uses Meta's Official Cloud API for WhatsApp.

1.  **Meta for Developers**:
    *   Go to Meta for Developers ([developers.facebook.com](https://developers.facebook.com/)).
    *   Create an app and set up the WhatsApp Business Platform.
    *   Obtain your **Permanent Access Token** and **WhatsApp Phone Number ID**.

2.  **Environment Variables**:
    Create a `.env` file in your project root (or set system-wide environment variables) with the following:

    ```
    WA_TOKEN="YOUR_WHATSAPP_PERMANENT_ACCESS_TOKEN"
    WA_PHONE_ID="YOUR_WHATSAPP_PHONE_NUMBER_ID"
    ```

    Ensure that the phone number you are using for testing or production is registered with the WhatsApp Business Platform and added to your Meta app.

## Running the Application

To start the Streamlit web application:

```bash
streamlit run app.py
```

The application will open in your web browser.

## Running the Notification Service

To start the WhatsApp notification background service:

```bash
python WA_notify.py
```

This script continuously scans the employment database and sends relevant notifications. If deployed in a cloud environment such as GitHub Actions, it runs as a scheduled scan.

## Admin Credentials

The default administrator credentials are:

*   **Username**: `admin`
*   **Password**: `admin@SSS`

It is highly recommended to change these default credentials after your initial setup.
