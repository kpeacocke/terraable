FROM mcr.microsoft.com/devcontainers/python:3.11

# The yarn apt repository bundled in this base image has a missing/expired GPG
# key (FF7CB5667B542092084BBDC562D54FD4003F6525) which causes `apt-get update`
# to exit non-zero.  The Terraform devcontainer feature install script treats
# any apt-get failure as fatal, so we remove the broken repo source before
# feature layers run.
RUN set -eux; \
    rm -f /etc/apt/sources.list.d/yarn.list \
          /etc/apt/sources.list.d/yarn.sources \
          /etc/apt/trusted.gpg.d/yarn.gpg; \
    apt-get clean; \
    # SonarQube for IDE uses a Java language server. Install a minimal runtime
    # so analysis works reliably in fresh containers.
    apt-get update; \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless; \
    rm -rf /var/lib/apt/lists/*; \
    # Provide a stable Java home path for tools that fail to auto-detect JRE.
    JAVA_BIN="$(readlink -f "$(command -v java)")"; \
    JAVA_HOME="$(dirname "$(dirname "$JAVA_BIN")")"; \
    ln -sfn "$JAVA_HOME" /opt/java-home; \
    # Some language servers expect /etc/machine-id to exist in containers.
    if [ ! -s /etc/machine-id ]; then \
      if command -v dbus-uuidgen >/dev/null 2>&1; then \
        dbus-uuidgen --ensure=/etc/machine-id; \
      else \
        cat /proc/sys/kernel/random/uuid > /etc/machine-id; \
      fi; \
    fi
