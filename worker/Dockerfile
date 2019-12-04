FROM ubuntu:18.04
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ADD ./credentials.json .
ENV GOOGLE_APPLICATION_CREDENTIALS="credentials.json"
ADD ./worker-install.sh .
RUN chmod +x worker-install.sh
RUN ./worker-install.sh
ADD ./worker-server.py .
CMD nohup python3 worker-server.py
