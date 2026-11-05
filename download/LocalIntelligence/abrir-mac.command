#!/bin/bash
# macOS: dê dois cliques neste arquivo. Na primeira vez, se o macOS bloquear, clique com o botão direito → Abrir.
cd "$(dirname "$0")" || exit 1
exec bash ./abrir-linux.sh
