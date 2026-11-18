from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from src.config import settings
from src.shared.database import Base
from src.web.pir import models as pir_models
from src.web.assignments import models as assignment_models
from src.web.regulations import models as regulation_models
from src.web.events import models as event_models
from src.web.auth import models as auth_models
from src.web.users import models as user_models
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
