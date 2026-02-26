ARG BUILD_FROM
FROM $BUILD_FROM

ARG LIBCEC_VERSION

WORKDIR /usr/src

RUN \
    apk add --no-cache \
        python3 \
        py3-paho-mqtt \
        eudev-libs \
        p8-platform \
        ca-certificates \
    && apk add --no-cache --virtual .build-dependencies \
        build-base \
        cmake \
        eudev-dev \
        git \
        p8-platform-dev \
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
        .. \
    && make -j$(nproc) \
    && make install \
    && python3 -c "import cec; print('cec python module OK:', cec)" \
    && apk del --no-cache .build-dependencies \
    && rm -rf /usr/src/*

COPY src/ /app/src/

WORKDIR /
COPY rootfs /

RUN chmod +x /etc/services.d/cec_mqtt_bridge/run
