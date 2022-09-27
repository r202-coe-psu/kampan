FROM debian:sid
RUN echo 'deb http://mirrors.psu.ac.th/debian/ sid main contrib non-free' > /etc/apt/sources.list
# RUN echo 'deb http://mirror.kku.ac.th/debian/ sid main contrib non-free' >> /etc/apt/sources.list
RUN apt update && apt upgrade -y
RUN apt install -y python3 python3-dev python3-pip python3-venv npm git locales
RUN sed -i '/th_TH.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG th_TH.UTF-8 
ENV LANGUAGE th_TH:en 
ENV LC_ALL th_TH.UTF-8


RUN python3 -m venv /venv
ENV PYTHON=/venv/bin/python3
RUN $PYTHON -m pip install wheel poetry gunicorn

WORKDIR /app
COPY poetry.lock pyproject.toml /app/
RUN $PYTHON -m poetry config virtualenvs.create false && $PYTHON -m poetry install --no-interaction --no-dev

COPY kampan/web/static/package.json kampan/web/static/package-lock.json kampan/web/static/
RUN npm install --prefix kampan/web/static


COPY . /app
ENV KAMPAN_SETTINGS=/app/kampan-production.cfg

# For brython
RUN cd /app/kampan/web/static/brython; \
    for i in $(ls -d */); \
    do \
    cd $i; \
    python3 -m brython --make_package ${i%%/}; \
    mv *.brython.js ..; \
    cd ..; \
    done
