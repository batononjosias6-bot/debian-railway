FROM debian:bookworm-slim

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        android-sdk-libsparse-utils \
        attr \
        binutils \
        brotli \
        ca-certificates \
        cpio \
        curl \
        e2fsprogs \
        erofs-utils \
        file \
        git \
        jq \
        lz4 \
        neofetch \
        p7zip-full \
        python3 \
        python3-pip \
        ripgrep \
        rsync \
        unzip \
        wget \
        xxd \
        xz-utils \
        zip \
        zstd && \
    python3 -m pip install --break-system-packages --no-cache-dir gdown && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN wget -qO /bin/ttyd https://github.com/tsl0922/ttyd/releases/download/1.7.3/ttyd.x86_64 && \
    chmod +x /bin/ttyd

COPY scripts/ /opt/josia/bin/
RUN chmod +x /opt/josia/bin/*

RUN echo "neofetch" >> /root/.bashrc && \
    echo "cd /data/tecno" >> /root/.bashrc

EXPOSE $PORT

CMD ["/bin/bash", "-c", "\
    mkdir -p /data/tecno /tmp/josia-firmware && \
    echo \"export PS1='\\[\\033[01;31m\\]$USERNAME@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ '\" >> /root/.bashrc && \
    /bin/ttyd -p $PORT -c $USERNAME:$PASSWORD /bin/bash"]
