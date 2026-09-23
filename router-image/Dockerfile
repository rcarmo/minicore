# Reuse pinned upstream runtime libraries; replace FRR with reviewed plain-IP build.
FROM quay.io/frrouting/frr:10.4.1@sha256:f1dd8182ca8ebd76421378702b95d1553fd7285d63db170640eefeb6f989c9dd AS builder
RUN apk add --no-cache autoconf automake libtool make gcc g++ musl-dev linux-headers bison flex python3-dev py3-pytest json-c-dev c-ares-dev libcap-dev readline-dev pcre2-dev elfutils-dev bash curl
WORKDIR /build
RUN curl -fsSL https://codeload.github.com/FRRouting/frr/tar.gz/refs/tags/frr-10.4.1 -o frr.tar.gz \
 && echo '8e4003eaba168626c5ea7a6735f2c85c87b04214e6f8c8f2715b21f8ae40970b  frr.tar.gz' | sha256sum -c - \
 && tar -xzf frr.tar.gz
WORKDIR /build/frr-frr-10.4.1
# Only the capability declarations are changed. Kernel privilege checks stay enabled.
RUN python3 - <<'PY'
from pathlib import Path
import re
for name in ('zebra/main.c','bgpd/bgp_main.c','ospfd/ospf_main.c','mgmtd/mgmt_main.c'):
    p=Path(name); text=p.read_text(); assert text.count('ZCAP_SYS_ADMIN')==1, name
    p.write_text(re.sub(r'\bZCAP_SYS_ADMIN\s*,?', '/* Minicore: no SYS_ADMIN */', text))
PY
RUN apk add --no-cache protobuf-c-dev protobuf-c-compiler && ./bootstrap.sh && ./configure --prefix=/usr --sysconfdir=/etc --localstatedir=/var --sbindir=/usr/lib/frr --libdir=/usr/lib --enable-user=frr --enable-group=frr --enable-vty-group=frrvty --enable-vtysh --disable-doc --disable-snmp --disable-ripd --disable-ripngd --disable-ospf6d --disable-isisd --disable-ldpd --disable-nhrpd --disable-eigrpd --disable-babeld --disable-pimd --disable-pim6d --disable-pbrd --disable-bfdd --disable-fabricd --disable-vrrpd --disable-pathd --disable-bgp-vnc --disable-bgp-bmp --disable-scripting
RUN make -j2 && make DESTDIR=/stage install

FROM quay.io/frrouting/frr:10.4.1@sha256:f1dd8182ca8ebd76421378702b95d1553fd7285d63db170640eefeb6f989c9dd
COPY --from=builder /stage/usr/ /usr/
COPY router-image/node-health /usr/local/bin/node-health
RUN chmod 755 /usr/local/bin/node-health \
 && printf 'service integrated-vtysh-config\n' > /etc/frr/vtysh.conf

RUN apk add --no-cache openssh-server openssh-keygen \
 && adduser -D -u 11001 -s /bin/sh diagnostic \
 && addgroup diagnostic frrvty \
 && passwd -u diagnostic \
 && mkdir -p /etc/minicore /run/sshd
COPY router-image/dispatcher/node_dispatcher.py /usr/local/bin/minicore-dispatch
COPY router-image/sshd_config /etc/ssh/sshd_config
COPY router-image/start-node /usr/local/bin/start-node
RUN chmod 755 /usr/local/bin/minicore-dispatch /usr/local/bin/start-node
CMD ["/usr/local/bin/start-node"]
COPY router-image/dispatcher/fault_dispatcher.py /usr/local/bin/minicore-fault
RUN chmod 755 /usr/local/bin/minicore-fault
