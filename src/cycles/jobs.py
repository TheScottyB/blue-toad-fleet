"""Launch one configured Cloud Run Job for one immutable cycle."""

from __future__ import annotations

import os

from src.cycles.model import CycleRequest


class JobLaunchError(RuntimeError):
    pass


class CloudRunJobLauncher:
    def __init__(
        self,
        project: str,
        region: str,
        job_name: str,
        bucket: str,
        session=None,
    ):
        self.project = project
        self.region = region
        self.job_name = job_name
        self.bucket = bucket.removeprefix("gs://").rstrip("/")
        self._session = session

    @property
    def configured(self) -> bool:
        return all((self.project, self.region, self.job_name, self.bucket))

    def _authorized_session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self._session = AuthorizedSession(credentials)
        return self._session

    def launch(self, request: CycleRequest) -> str:
        if not self.configured:
            raise JobLaunchError("Cloud Run cycle job is not configured")
        url = (
            "https://run.googleapis.com/v2/projects/"
            f"{self.project}/locations/{self.region}/jobs/{self.job_name}:run"
        )
        payload = {
            "overrides": {
                "containerOverrides": [{
                    "env": [
                        {"name": "BTF_CYCLE_BUCKET", "value": self.bucket},
                        {"name": "BTF_CYCLE_ID", "value": request.cycle_id},
                        {"name": "BTF_SHOP_ID", "value": request.shop_id},
                    ]
                }],
                "taskCount": 1,
                "timeout": "7200s",
            }
        }
        response = self._authorized_session().post(url, json=payload, timeout=30)
        if not 200 <= response.status_code < 300:
            raise JobLaunchError(
                f"Cloud Run jobs.run returned {response.status_code}: "
                f"{response.text[:500]}")
        data = response.json()
        operation = data.get("name")
        if not operation:
            raise JobLaunchError("Cloud Run jobs.run returned no operation name")
        return operation


def open_job_launcher() -> CloudRunJobLauncher | None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    region = os.environ.get("CLOUD_RUN_REGION", "us-central1")
    job = os.environ.get("BTF_CYCLE_JOB", "")
    bucket = os.environ.get("BTF_CYCLE_BUCKET", "")
    if not all((project, region, job, bucket)):
        return None
    return CloudRunJobLauncher(project, region, job, bucket)
