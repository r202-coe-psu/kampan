FROM debian:sid
RUN echo 'deb http://mirrors.psu.ac.th/debian/ sid main contrib non-free' > /etc/apt/sources.list
# RUN echo 'deb http://mirror.kku.ac.th/debian/ sid main contrib non-free' >> /etc/apt/sources.list
RUN apt update && apt upgrade -y
RUN apt install -y python3 python3-dev python3-pip python3-venv npm git locales
RUN sed -i '/th_TH.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG th_TH.UTF-8 
ENV LANGUAGE th_TH:en 
ENV LC_ALL th_TH.UTF-8
COPY . /app
WORKDIR /app

RUN npm install --prefix kampan/web/static

ENV KAMPAN_SETTINGS=/app/kampan-production.cfg

RUN ln -s $(command -v python3) /usr/bin/python
RUN pip3 install poetry
RUN poetry config virtualenvs.create false && poetry install --no-interaction
ENV PYTHONPATH $(pwd):/usr/lib/python3.9/site-packages:$PYTHONPATH

# For brython
# RUN cd /app/kampan/web/static/brython; \
#     for i in $(ls -d */); \
#     do \
#     cd $i; \
#     python3 -m brython --make_package ${i%%/}; \
#     mv *.brython.js ..; \
#     cd ..; \
#     done
