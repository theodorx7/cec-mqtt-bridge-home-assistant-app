FROM ghcr.io/home-assistant/base:latest
ARG LIBCEC_VERSION=8.1.7

WORKDIR /usr/src

RUN \
    apk add --no-cache \
        python3 \
        py3-paho-mqtt \
        eudev-libs \
        ca-certificates \
    && apk add --no-cache --virtual .build-dependencies \
        build-base \
        cmake \
        eudev-dev \
        git \
        swig \
        linux-headers \
        python3-dev \
    && git clone --depth 1 -b libcec-${LIBCEC_VERSION} \
        "https://github.com/Pulse-Eight/libcec" libcec \
    && mkdir -p libcec/build \
    && cd libcec/build \
    && cmake \
        -DCMAKE_INSTALL_PREFIX:PATH=/usr \
        -DHAVE_LINUX_API=1 \
        -DDISABLE_CLIENT=1 \
        -DDISABLE_STATIC=1 \
        .. \
    && make -j$(nproc) \
    && make install \
    && python3 -c "import cec; print('cec python module OK:', cec)" \
    && apk del --no-cache .build-dependencies \
    && rm -rf /usr/src/*

COPY cec_mqtt_bridge/ /app/cec_mqtt_bridge/
COPY run.sh /
RUN chmod a+x /run.sh
WORKDIR /

LABEL \
    io.hass.name="HDMI-CEC MQTT Bridge" \
    io.hass.description="Connecting HDMI-CEC devices to your home automation system." \
    io.hass.version="2.0.2" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    io.hass.url="https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app" \
    org.opencontainers.image.title="Home Assistant App: HDMI-CEC MQTT Bridge" \
    org.opencontainers.image.description="Connecting HDMI-CEC devices to your home automation system." \
    org.opencontainers.image.source="https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app" \
    org.opencontainers.image.licenses="Unlicense"

CMD ["/run.sh"]
