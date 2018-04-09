FROM arm32v7/python:2

WORKDIR /usr/src/HTTPAceProxy

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./acehttp.py" ]

