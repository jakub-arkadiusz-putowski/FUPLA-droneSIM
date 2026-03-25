FROM ubuntu:22.04

# Konfiguracja środowiska
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Warsaw

# Instalacja podstawowych narzędzi
RUN apt-get update && apt-get install -y \
    sudo \
    git \
    wget \
    curl \
    nano \
    lsb-release \
    gnupg \
    build-essential \
    joystick \
    jstest-gtk \
    && rm -rf /var/lib/apt/lists/*

# Tworzenie użytkownika z takimi samymi uprawnieniami jak Twój host
ARG USERNAME=developer
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME -s /bin/bash \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && usermod -aG dialout,plugdev $USERNAME

USER $USERNAME
WORKDIR /workspace

CMD ["/bin/bash"]