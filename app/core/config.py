from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS / Athena
    aws_region: str = "eu-west-2"
    athena_database: str = "cur_v2_database"
    athena_workgroup: str = "primary"

    # App
    app_env: str = "development"
    api_key: SecretStr = Field(min_length=32)

    # Analytical Platform (AP). If athena_role_arn is unset, the app
    # uses its own credentials, COATs bucket and region (as before)
    athena_role_arn: str | None = None
    athena_region: str | None = None
    athena_output_base: str | None = None  # UserId is added at runtime
    athena_role_session_name: str = "coat-cost-api"

    @property
    def athena_output_location(self) -> str:
        if self.app_env == "production":
            return "s3://coat-production-cur-v2-hourly/athena-results"
        return "s3://coat-development-athena-output-clickops/Unsaved"

    @property
    def athena_client_region(self) -> str:
        return self.athena_region or self.aws_region

    class Config:
        env_file = ".env"


# api_key is loaded from the environment by pydantic-settings
settings = Settings()  # type: ignore[call-arg]
