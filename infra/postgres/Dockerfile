# PostGIS + pgvector in one image. Neither upstream image ships both.
FROM postgis/postgis:16-3.4

ARG PGVECTOR_VERSION=v0.8.0

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential git postgresql-server-dev-16 \
      clang-13 \
      hunspell hunspell-el \
 && git clone --branch ${PGVECTOR_VERSION} --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
 && make -C /tmp/pgvector OPTFLAGS="" \
 && cp /tmp/pgvector/vector.so /usr/lib/postgresql/16/lib/ \
 && cp /tmp/pgvector/vector.control /usr/share/postgresql/16/extension/ \
 && cp /tmp/pgvector/sql/*.sql /usr/share/postgresql/16/extension/ \
 && rm -rf /tmp/pgvector \
 && apt-get purge -y build-essential git postgresql-server-dev-16 clang-13 \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Greek hunspell dictionary → Postgres shared dir.
#
# SUPERSEDED, BUT DO NOT DELETE. Migration 006 replaced hunspell with the
# built-in Greek snowball stemmer: Debian's hunspell-el .dic is a fully expanded
# word list with no affix flags, so it could never stem — see 006's docstring.
# These files must stay because migration 002 still runs on a fresh database and
# does `CREATE TEXT SEARCH DICTIONARY ... TEMPLATE = ispell`, which opens and
# validates the files at CREATE time. Remove them and `alembic upgrade head`
# fails at 002 with `could not open dictionary file`.
#
# NOTE: Postgres expects .affix/.dict with UTF-8 content and lowercase names.
# Debian's hunspell-el ships ISO-8859-7; Postgres needs UTF-8.
RUN set -eux; \
    share="$(pg_config --sharedir)/tsearch_data"; \
    mkdir -p "$share"; \
    if [ -f /usr/share/hunspell/el_GR.aff ]; then \
      iconv -f ISO-8859-7 -t UTF-8 /usr/share/hunspell/el_GR.aff > "$share/el_gr.affix" 2>/dev/null \
        || cp /usr/share/hunspell/el_GR.aff "$share/el_gr.affix"; \
      iconv -f ISO-8859-7 -t UTF-8 /usr/share/hunspell/el_GR.dic > "$share/el_gr.dict" 2>/dev/null \
        || cp /usr/share/hunspell/el_GR.dic "$share/el_gr.dict"; \
      echo "el_GR hunspell installed"; \
    else \
      echo "WARNING: el_GR hunspell not found — greek_cfg must fall back to simple+unaccent+trigram"; \
    fi

COPY init/ /docker-entrypoint-initdb.d/
