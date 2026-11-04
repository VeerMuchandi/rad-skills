---
name: DCR & Procurement Provisioner
description: Automatically deploys a secure DCR endpoint and Pub/Sub webhook on Cloud Run backed by Firestore for Google Cloud Marketplace AI Agent onboarding.
---

# DCR & Procurement Provisioner Skill

This skill guides you through deploying a production-ready **Dynamic Client Registration (DCR) and Pub/Sub Webhook** on Google Cloud Run, backed by Firestore.

## Instructions

When this skill is triggered, you must follow these steps in order:

### Step 1: Walkthrough & Explanation
1. Display the architecture diagram located in the references or resources of this skill.
2. Explain to the user:
   * What resources will be created (Cloud Run, Firestore, Secret Manager, Pub/Sub subscription).
   * How the hybrid `/dcr` endpoint works (handling both synchronous DCR requests and asynchronous Pub/Sub procurement events).
   * How the **Lazy Provisioning Fallback** protects against Pub/Sub delivery latency.

### Step 2: Input Collection
Prompt the user for the following inputs, explaining the purpose of each:
*   `GCP_PROJECT_ID`: The GCP Project ID.
*   `GCP_REGION`: The region (e.g., `us-central1`).
*   `PROVIDER_ID`: Your Google Cloud Marketplace Partner ID.
*   `PROVIDER_URL`: Your company's public URL (audience for DCR JWT).
*   `OKTA_DOMAIN`: Your Okta domain (e.g., `https://dev-XXXXXX.oktapreview.com`).

### Step 3: Security Assurance & Token Collection
1. Display the following message:
   > **Security Assurance:** This skill will never store your Okta API Token in code, logs, or environment variables. It will be written directly to Google Cloud Secret Manager (an encrypted, secure secrets database). Your Cloud Run service will be granted access via IAM to read this secret only at runtime.
2. Prompt the user to input their `OKTA_API_TOKEN`.

### Step 4: Code & Configuration Generation
1. Create a directory named `dcr_provisioner_deployment` in the user's workspace.
2. Copy the Terraform templates from this skill's `resources/terraform/` folder into `dcr_provisioner_deployment/terraform/`. Customize the variables in `terraform/terraform.tfvars` with the collected inputs.
3. Copy the application source code from this skill's `resources/app/` folder into `dcr_provisioner_deployment/app/`. Configure the environment variables in the Cloud Run deployment block.

### Step 5: Provision Infrastructure
1. Run `terraform init` and `terraform apply -auto-approve` inside `dcr_provisioner_deployment/terraform/`.
2. Wait for the resources (Firestore, Secret Manager, Service Account) to be created.

### Step 6: Store Secrets
1. Write the `OKTA_API_TOKEN` directly into the newly created Secret Manager secret (`okta-api-token`) using the `gcloud` CLI.

### Step 7: Build & Deploy to Cloud Run
1. Run `gcloud builds submit --tag gcr.io/GCP_PROJECT_ID/dcr-webhook dcr_provisioner_deployment/app/` to build the container.
2. Deploy the container to Cloud Run, ensuring it is associated with the newly created Service Account and has the required environment variables.
3. Enable Pub/Sub push subscription authentication (OIDC) using the Service Account.

### Step 8: Output & Handshake Checklist
Print a success message containing:
*   The DCR URL: `https://<cloud-run-url>/dcr`
*   Instructions on:
    1. Adding this DCR URL to the Google Cloud Producer Portal.
    2. Adding the redirect URIs to Okta.
    3. Testing the registration.
