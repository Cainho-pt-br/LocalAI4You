-- Painel v3: exclusão de acessos próprios (sessões ignoradas + data de corte + filtro Vercel/dev),
-- janela configurável (7 a 90 dias) e métricas de monetização, SEO por placa, CTAs e dispositivos.

create table if not exists privado.sessoes_ignoradas (
  sessao text primary key,
  motivo text not null default 'dono',
  criado timestamptz not null default now()
);
revoke all on privado.sessoes_ignoradas from public, anon, authenticated;

create table if not exists privado.painel_config (
  chave text primary key,
  valor text,
  atualizado timestamptz not null default now()
);
revoke all on privado.painel_config from public, anon, authenticated;

-- Ações administrativas do painel (sempre protegidas por senha).
create or replace function public.painel_acao(p_senha text, p_acao text, p_valor text default null)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_ts timestamptz;
begin
  if p_senha is null or not exists (select 1 from privado.painel_acesso where senha = p_senha) then
    perform pg_sleep(1); raise exception 'senha incorreta';
  end if;

  if p_acao = 'ignorar_sessao' then
    if p_valor is not null and length(trim(p_valor)) between 4 and 40 then
      insert into privado.sessoes_ignoradas (sessao, motivo)
      values (left(trim(p_valor), 40), 'dono')
      on conflict (sessao) do nothing;
    end if;
    return jsonb_build_object('ok', true, 'sessoes_ignoradas', (select count(*) from privado.sessoes_ignoradas));

  elsif p_acao = 'ignorar_antes' then
    if p_valor is null or trim(p_valor) = '' then
      v_ts := now();
    else
      v_ts := p_valor::timestamptz;
    end if;
    insert into privado.painel_config (chave, valor, atualizado)
    values ('ignorar_antes', v_ts::text, now())
    on conflict (chave) do update set valor = excluded.valor, atualizado = now();
    return jsonb_build_object('ok', true, 'ignorar_antes', v_ts);

  elsif p_acao = 'limpar_corte' then
    delete from privado.painel_config where chave = 'ignorar_antes';
    return jsonb_build_object('ok', true, 'ignorar_antes', null);

  else
    raise exception 'ação inválida';
  end if;
end $$;
revoke all on function public.painel_acao(text, text, text) from public;
grant execute on function public.painel_acao(text, text, text) to anon, authenticated;

-- Remove assinatura antiga de 1 parâmetro para evitar ambiguidade com a nova (default p_dias = 30).
drop function if exists public.painel_resumo(text);

create or replace function public.painel_resumo(p_senha text, p_dias int default 30)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  r jsonb;
  v_dias int := greatest(7, least(coalesce(p_dias, 30), 90));
  v_corte timestamptz;
begin
  if p_senha is null or not exists (select 1 from privado.painel_acesso where senha = p_senha) then
    perform pg_sleep(1); raise exception 'senha incorreta';
  end if;

  select nullif(valor, '')::timestamptz into v_corte
  from privado.painel_config where chave = 'ignorar_antes';

  with
    brutos as (
      select * from privado.eventos
      where criado > now() - make_interval(days => greatest(v_dias, 14) + 1)
    ),
    ev as (
      select * from brutos
      where host not like '%-projects.vercel.app'
        and host not like 'localhost%'
        and host not like '127.%'
        and coalesce(origem, '') not in ('vercel.com', 'localhost')
        and (sessao is null or sessao not in (select sessao from privado.sessoes_ignoradas))
        and (v_corte is null or criado >= v_corte)
    ),
    e_per as (
      select * from ev where criado > now() - make_interval(days => v_dias)
    ),
    ses as (
      select sessao,
             bool_or(novo) novo,
             max(dispositivo) disp,
             max(idioma) idioma,
             bool_or(tipo = 'radar') viu_radar,
             bool_or(tipo = 'calculadora') usou_calc,
             bool_or(tipo = 'copiar') copiou,
             bool_or(tipo = 'loja') loja,
             bool_or(tipo = 'apoio') apoio,
             bool_or(tipo = 'download') baixou,
             count(*) filter (where tipo in ('pagina', 'aba')) abas
      from e_per
      where sessao is not null
      group by 1
    ),
    sem as (
      select sum(case when criado > now() - interval '7 days' then 1 else 0 end) atual,
             sum(case when criado <= now() - interval '7 days' and criado > now() - interval '14 days' then 1 else 0 end) anterior,
             tipo
      from (select distinct on (sessao, tipo) sessao, tipo, criado from ev where sessao is not null order by sessao, tipo, criado desc) d
      group by tipo
    ),
    b as (select * from privado.benchmarks)
  select jsonb_build_object(
    'versao', 3,
    'dias', v_dias,
    'gerado', now(),
    'meta', jsonb_build_object(
      'ignorar_antes', v_corte,
      'sessoes_ignoradas', (select count(*) from privado.sessoes_ignoradas),
      'eventos_excluidos', (select count(*) from brutos) - (select count(*) from ev)
    ),
    'totais', jsonb_build_object(
      'visitas_30d', (select count(*) from ses),
      'novas_pct', (select round(100.0 * count(*) filter (where novo) / nullif(count(*), 0)) from ses),
      'recorrentes_pct', (select round(100.0 * count(*) filter (where not coalesce(novo, true)) / nullif(count(*), 0)) from ses),
      'celular_pct', (select round(100.0 * count(*) filter (where disp = 'celular') / nullif(count(*), 0)) from ses),
      'abas_por_visita', (select round(avg(abas), 1) from ses),
      'comandos_copiados', (select count(*) from e_per where tipo = 'copiar'),
      'cliques_loja', (select count(*) from e_per where tipo = 'loja'),
      'cliques_apoio', (select count(*) from e_per where tipo = 'apoio'),
      'downloads', (select count(*) from e_per where tipo = 'download'),
      'sessoes_radar', (select count(*) filter (where viu_radar) from ses),
      'sessoes_copiar', (select count(*) filter (where copiou) from ses),
      'sessoes_loja', (select count(*) filter (where loja) from ses),
      'sessoes_apoio', (select count(*) filter (where apoio) from ses),
      'sessoes_download', (select count(*) filter (where baixou) from ses),
      'benchmarks', (select count(*) from b),
      'maquinas', (select count(distinct hardware) from b),
      'benchmarks_7d', (select count(*) from b where criado > now() - interval '7 days')
    ),
    'semana', (select coalesce(jsonb_object_agg(tipo, jsonb_build_object('atual', atual, 'anterior', anterior)), '{}') from sem),
    'funil', (select jsonb_build_array(
      jsonb_build_object('etapa', 'Visitaram o site', 'n', count(*)),
      jsonb_build_object('etapa', 'Viram o Radar', 'n', count(*) filter (where viu_radar)),
      jsonb_build_object('etapa', 'Copiaram um comando', 'n', count(*) filter (where copiou)),
      jsonb_build_object('etapa', 'Clicaram em loja (afiliado)', 'n', count(*) filter (where loja)),
      jsonb_build_object('etapa', 'Baixaram o app', 'n', count(*) filter (where baixou))
    ) from ses),
    'diario', (select coalesce(jsonb_agg(x order by x.dia desc), '[]') from (
      select date_trunc('day', criado at time zone 'America/Sao_Paulo')::date dia,
             count(distinct sessao) visitas,
             count(distinct sessao) filter (where tipo = 'radar') radar,
             count(*) filter (where tipo = 'copiar') comandos,
             count(*) filter (where tipo = 'loja') lojas,
             count(*) filter (where tipo = 'download') downloads
      from e_per group by 1
    ) x),
    'origens', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(utm_source, origem, '(direto)') origem,
             count(distinct sessao) visitas,
             round(100.0 * count(distinct sessao) filter (where tipo = 'radar') / nullif(count(distinct sessao), 0)) pct_radar,
             count(distinct sessao) filter (where tipo = 'copiar') copiaram,
             count(distinct sessao) filter (where tipo = 'download') baixaram
      from e_per group by 1 order by 2 desc limit 15
    ) x),
    'dispositivos', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(disp, '?') dispositivo,
             count(*) visitas,
             round(100.0 * count(*) filter (where viu_radar) / nullif(count(*), 0)) pct_radar,
             round(100.0 * count(*) filter (where copiou) / nullif(count(*), 0)) pct_copiar,
             round(100.0 * count(*) filter (where baixou) / nullif(count(*), 0)) pct_download
      from ses group by 1 order by 2 desc
    ) x),
    'paginas_placa', (select coalesce(jsonb_agg(x), '[]') from (
      select dados->>'hardware' hardware,
             coalesce(dados->>'idioma', left(idioma, 2), '?') idioma,
             count(distinct sessao) visitas,
             count(*) filter (where tipo = 'copiar') copias,
             count(*) filter (where tipo = 'loja') lojas
      from e_per
      where dados ? 'hardware' and nullif(dados->>'hardware', '') is not null
      group by 1, 2 order by 3 desc limit 15
    ) x),
    'lojas', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(dados->>'loja', '?') loja,
             coalesce(dados->>'busca', dados->>'hardware', '—') busca,
             coalesce(dados->>'origem', aba, '—') origem,
             count(*) cliques,
             count(distinct sessao) visitas
      from e_per where tipo = 'loja'
      group by 1, 2, 3 order by 4 desc limit 20
    ) x),
    'ctas', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(dados->>'origem', dados->>'acao', '?') origem,
             count(*) cliques,
             count(distinct sessao) visitas
      from e_per where tipo = 'uso'
      group by 1 order by 2 desc limit 15
    ) x),
    'usos', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(nullif(dados->>'uso', ''), 'geral') uso, count(distinct sessao) visitas
      from e_per where tipo = 'radar' group by 1 order by 2 desc limit 12
    ) x),
    'hardware_site', (select coalesce(jsonb_agg(x), '[]') from (
      select dados->>'perfil' hardware,
             count(distinct sessao) visitas,
             count(distinct sessao) filter (where coalesce(dados->>'palpite', 'exemplo') <> 'exemplo') detectado
      from e_per where tipo in ('radar', 'calculadora') and dados ? 'perfil'
      group by 1 order by 2 desc limit 15
    ) x),
    'modelos_copiados', (select coalesce(jsonb_agg(x), '[]') from (
      select regexp_replace(dados->>'comando', '^ollama (pull|run) ', '') modelo, count(*) copias
      from e_per where tipo = 'copiar' group by 1 order by 2 desc limit 15
    ) x),
    'abas', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(dados->>'aba', aba) aba, count(distinct sessao) visitas
      from e_per where tipo in ('pagina', 'aba') group by 1 order by 2 desc limit 10
    ) x),
    'idiomas', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(nullif(left(idioma, 2), ''), '?') idioma, count(*) visitas
      from ses group by 1 order by 2 desc limit 8
    ) x),
    'downloads_origem', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(dados->>'origem', '?') origem, count(*) n
      from e_per where tipo = 'download' group by 1 order by 2 desc
    ) x),
    'placas_comunidade', (select coalesce(jsonb_agg(x), '[]') from (
      select coalesce(hardware->>'gpu', 'Sem placa (' || coalesce(hardware->>'ram_gb', '?') || ' GB RAM)') placa,
             count(*) envios, count(distinct modelo) modelos
      from b group by 1 order by 2 desc limit 20
    ) x),
    'modelos_comunidade', (select coalesce(jsonb_agg(x), '[]') from (
      select modelo, coalesce(hardware->>'gpu', 'Sem placa') placa, count(*) envios,
             round(avg((resultado->>'tps')::numeric), 1) tps_medio,
             round(avg((select avg((v->>'nota')::numeric) from jsonb_each(resultado->'papeis') e(k, v))), 1) nota_media
      from b group by 1, 2 order by 3 desc, 1 limit 40
    ) x)
  ) into r;
  return r;
end $$;

revoke all on function public.painel_resumo(text, int) from public;
grant execute on function public.painel_resumo(text, int) to anon, authenticated;
