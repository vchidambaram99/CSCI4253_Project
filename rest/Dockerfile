FROM ubuntu:18.04
RUN apt-get update
RUN apt-get -y install python3 python3-pip
RUN pip3 install flask pika redis requests google-cloud-storage google-cloud-logging
ADD ./rest-server.py .
ADD ./credentials.json .
ENV FLASK_APP=rest-server.py
ENV GOOGLE_APPLICATION_CREDENTIALS="credentials.json"
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
CMD nohup flask run -h 0.0.0.0
