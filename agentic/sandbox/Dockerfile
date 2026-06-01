# 1.使用ubuntu基础镜像来源
FROM ubuntu:24.04

# 2.安装过程避免交互式提示并设置主机名
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox
ARG APT_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu
ARG APT_PORTS_MIRROR=http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports

# 3.按需切换Ubuntu软件源
RUN set -eux; \
    if [ -n "$APT_MIRROR" ] && [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i "s|http://archive.ubuntu.com/ubuntu|$APT_MIRROR|g" /etc/apt/sources.list.d/ubuntu.sources; \
        sed -i "s|http://security.ubuntu.com/ubuntu|$APT_MIRROR|g" /etc/apt/sources.list.d/ubuntu.sources; \
    fi; \
    if [ -n "$APT_PORTS_MIRROR" ] && [ -f /etc/apt/sources.list.d/ubuntu.sources ]; then \
        sed -i "s|http://ports.ubuntu.com/ubuntu-ports|$APT_PORTS_MIRROR|g" /etc/apt/sources.list.d/ubuntu.sources; \
    fi; \
    if [ -n "$APT_MIRROR" ] && [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://archive.ubuntu.com/ubuntu/|$APT_MIRROR/|g" /etc/apt/sources.list; \
        sed -i "s|http://security.ubuntu.com/ubuntu/|$APT_MIRROR/|g" /etc/apt/sources.list; \
    fi; \
    if [ -n "$APT_PORTS_MIRROR" ] && [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://ports.ubuntu.com/ubuntu-ports/|$APT_PORTS_MIRROR/|g" /etc/apt/sources.list; \
    fi

# 4.更新和安装基础软件后并移除依赖
RUN set -eux; \
    apt_opts="-o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"; \
    apt_retry() { \
        for attempt in 1 2 3 4 5; do \
            if apt-get $apt_opts "$@"; then \
                return 0; \
            fi; \
            if [ "$attempt" = 5 ]; then \
                return 1; \
            fi; \
            sleep 10; \
            apt-get $apt_opts update; \
        done; \
    }; \
    apt_install() { \
        apt_retry install -y --no-install-recommends "$@"; \
    }; \
    apt_retry update; \
    apt_install sudo bc curl wget gnupg ca-certificates supervisor locales language-pack-zh-hans; \
    apt_install python3 python3-venv python3-dev python3-pip; \
    apt_install xterm socat xvfb x11vnc websockify; \
    apt_install nodejs npm; \
    apt_install fonts-noto-cjk fonts-noto-color-emoji; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# 5.创建用户ubuntu并赋予sudo权限（如果不存在）
RUN id -u ubuntu >/dev/null 2>&1 || useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# 7.为pip3配置阿里云镜像源（使用 PIP_BREAK_SYSTEM_PACKAGES 环境变量）
RUN PIP_BREAK_SYSTEM_PACKAGES=1 pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 9.将npm镜像源设置为阿里云镜像源
RUN npm config set registry https://registry.npmmirror.com

# 10.安装Google Chrome浏览器
RUN set -eux; \
    wget --tries=5 -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-linux.gpg; \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux.gpg] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list; \
    apt_opts="-o Acquire::Retries=5 -o Acquire::http::Timeout=60 -o Acquire::https::Timeout=60"; \
    for attempt in 1 2 3 4 5; do \
        if apt-get $apt_opts update && apt-get $apt_opts install -y google-chrome-stable --no-install-recommends; then \
            break; \
        fi; \
        if [ "$attempt" = 5 ]; then \
            exit 1; \
        fi; \
        sleep 10; \
    done; \
    ln -sf /usr/bin/google-chrome /usr/bin/chromium; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# 11.安装中文字体和语言支持
RUN locale-gen zh_CN.UTF-8

# 12.设置默认编码
ENV LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:zh \
    LC_ALL=zh_CN.UTF-8

# 13.设置工作空间
WORKDIR /sandbox

# 14.拷贝项目依赖文件到工作空间并安装依赖（Ubuntu 24.04 需要 --break-system-packages + --ignore-installed）
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed -r requirements.txt

# 15.拷贝当前整个项目文件
COPY . .

# 16.将supervisord.conf拷贝至supervisor服务配置目录中
COPY supervisord.conf /etc/supervisor/conf.d/sandbox.conf

# 17.暴露端口: 8080(FastAPI) 9222(CDP) 5900(vnc)
EXPOSE 8080 9222 5900 5901

# 18.额外的环境变量配置
ENV CHROME_ARGS=""
ENV UVI_ARGS=""

# 19.使用supervisor管理所有进程
CMD ["supervisord", "-n", "-c", "/sandbox/supervisord.conf"]
