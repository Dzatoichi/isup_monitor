from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from src.config import settings
from src.shared.database import Base
from src.web.contracts import models as contract_models
from src.web.documents import models as document_models
from src.web.organizations import models as organization_models
from src.web.participants import models as participant_models
from src.web.projects import projects_model

# Импорты регистрируют модели в metadata для Alembic.
url = settings.CONNECT_ASYNC()
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
