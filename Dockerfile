FROM python:3.7
ENV PYTHONUNBUFFERED 1
RUN mkdir /backend
WORKDIR /backend
COPY . /backend/
CMD ["bash", "dev.sh"]
