FROM node:21-alpine


# 必要なパッケージをインストール
RUN apk update && apk add --no-cache \
    tzdata \
    gettext

# タイムゾーンの設定
RUN cp /usr/share/zoneinfo/Asia/Tokyo /etc/localtime && \
    echo "Asia/Tokyo" > /etc/timezone

# ロケールの設定
ENV LANG=ja_JP.UTF-8
ENV LANGUAGE=ja_JP:ja
ENV LC_ALL=ja_JP.UTF-8
 
WORKDIR /app

COPY package.json ./
COPY package-lock.json ./
RUN npm install

COPY . ./

EXPOSE 3001

CMD ["node", "backend.js"]
