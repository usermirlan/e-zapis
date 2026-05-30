# 1. Расмий Python имиджин негиз кылып алабыз
FROM python:3.11-slim

# 2. Терминалдагы логдорду дароо көрүү үчүн жөндөөлөр
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Контейнердин ичиндеги жумушчу папканы белгилейбиз
WORKDIR /app

# 4. Керектүү китепканалардын тизмесин көчүрөбүз
COPY requirements.txt /app/

# 5. Китепканаларды контейнердин ичине орнотобуз
RUN pip install --no-cache-dir -r requirements.txt

# 6. Долбоордун калган бардык файлдарын контейнерге көчүрөбүз
COPY . /app/

# 7. Django серверин иштетүүчү команда
CMD python manage.py migrate && python manage.py runserver 0.0.0.0:8000