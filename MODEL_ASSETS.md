# Model asset policy

- Do not commit model weights, customer media, evaluation samples, engine caches, or derived biometric templates.
- Every registered artifact must provide source, owner, license, redistribution decision, SHA-256, model card, input/output contract, evaluation report and regression samples.
- A production profile rejects fallback, placeholder, unverified digest and unapproved license states.
- Public examples may contain only synthetic inputs or assets with explicit redistribution permission.
- Portrait candidates such as YOLO, SCRFD, ArcFace, OSNet, RTMPose and OpenGait are capability references, not approved bundled assets.
- OCR and PDF runtimes must pass the same dependency, model and dataset license review before inclusion.
