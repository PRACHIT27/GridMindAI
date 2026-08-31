# Official Google Cloud product icons

Extracted from the official archive published at https://cloud.google.com/icons
(`google-cloud-icons.zip`), 2021-10 revision. Only the products this project
actually uses are kept.

| File | Used for |
|---|---|
| `cloud_run.svg` | the seven Cloud Run services |
| `firestore.svg` | the five isolated data stores |
| `vertexai.svg` | Gemini 3.5 inference |
| `identity_and_access_management.svg` | the IAM conditions enforcing isolation |
| `virtual_private_cloud.svg` | the private network boundary |
| `cloud_nat.svg` | egress from the VPC |
| `cloud_logging.svg` | the audit trail |
| `cloud_armor.svg` | stands in for Model Armor, which has no published icon |
| `artifact_registry.svg` | the container image |

They are flattened before embedding — see `docs/gcp_icons.py`. Each ships with
an internal stylesheet using generic class names (`.cls-1`, `.cls-2`), so
inlining several into one document would make every icon's classes collide and
render them all in whichever palette was declared last.
