"""
Rate limiter para evitar bloqueos de Google Trends.
"""
import time
import logging
from functools import wraps

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter simple que espera un tiempo fijo entre llamadas.
    """

    def __init__(self, seconds_between_calls: int = 60):
        self.seconds_between_calls = seconds_between_calls
        self.last_call_time = 0

    def wait(self):
        """Espera el tiempo necesario antes de la siguiente llamada."""
        import random

        current_time = time.time()
        time_since_last_call = current_time - self.last_call_time

        if time_since_last_call < self.seconds_between_calls:
            wait_time = self.seconds_between_calls - time_since_last_call
            # Agregar jitter aleatorio (±5%) para evitar patrones sincronizados
            jitter = random.uniform(-0.05, 0.05) * self.seconds_between_calls
            wait_time = max(0, wait_time + jitter)
            logger.info(f"Rate limiting: esperando {wait_time:.1f} segundos...")
            time.sleep(wait_time)

        self.last_call_time = time.time()

    def __call__(self, func):
        """Decorador para aplicar rate limiting a funciones."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            self.wait()
            return func(*args, **kwargs)
        return wrapper


def retry_with_backoff(max_retries: int = 3, base_delay: int = 30):
    """
    Decorador que reintenta una función con backoff exponencial.

    Args:
        max_retries: Número máximo de reintentos
        base_delay: Delay base en segundos (se multiplica en cada reintento)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    delay = base_delay * (2 ** attempt)

                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Intento {attempt + 1}/{max_retries} falló: {e}. "
                            f"Reintentando en {delay} segundos..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"Todos los {max_retries} intentos fallaron. "
                            f"Último error: {e}"
                        )

            raise last_exception
        return wrapper
    return decorator
