-- Painel v2 (funil, público, usos, semana contra semana) e resumo público da comunidade (só médias, sem nada individual).
create or replace function public.painel_resumo(p_senha text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r jsonb;
begin
  if p_senha is null or not exists (select 1 from privado.painel_acesso where senha = p_senha) then
    perform pg_sleep(1); raise exception 'senha incorreta';
  end if;
  with ev as (select * from privado.eventos where host not like '%-projects.vercel.app' and host not like 'localhost%' and criado > now() - interval '60 days'),
       e30 as (select * from ev where criado > now() - interval '30 days'),
       ses as (select sessao, bool_or(novo) novo, max(dispositivo) disp, max(idioma) idioma,
                      bool_or(tipo = 'radar') viu_radar, bool_or(tipo = 'calculadora') usou_calc,
                      bool_or(tipo = 'copiar') copiou, bool_or(tipo = 'loja') loja, bool_or(tipo = 'download') baixou,
                      count(*) filter (where tipo in ('pagina','aba')) abas
               from e30 where sessao is not null group by 1),
       sem as (select sum(case when criado > now() - interval '7 days' then 1 else 0 end) atual,
                      sum(case when criado <= now() - interval '7 days' and criado > now() - interval '14 days' then 1 else 0 end) anterior, tipo
               from (select distinct on (sessao, tipo) sessao, tipo, criado from ev) d group by tipo),
       b as (select * from privado.benchmarks)
  select jsonb_build_object(
    'gerado', now(),
    'totais', jsonb_build_object(
        'visitas_30d', (select count(*) from ses),
        'novas_pct', (select round(100.0 * count(*) filter (where novo) / nullif(count(*), 0)) from ses),
        'celular_pct', (select round(100.0 * count(*) filter (where disp = 'celular') / nullif(count(*), 0)) from ses),
        'abas_por_visita', (select round(avg(abas), 1) from ses),
        'benchmarks', (select count(*) from b), 'maquinas', (select count(distinct hardware) from b),
        'benchmarks_7d', (select count(*) from b where criado > now() - interval '7 days')),
    'semana', (select coalesce(jsonb_object_agg(tipo, jsonb_build_object('atual', atual, 'anterior', anterior)), '{}') from sem),
    'funil', (select jsonb_build_array(
        jsonb_build_object('etapa', 'Visitaram', 'n', count(*)),
        jsonb_build_object('etapa', 'Viram o Radar', 'n', count(*) filter (where viu_radar)),
        jsonb_build_object('etapa', 'Copiaram um comando ou foram a uma loja', 'n', count(*) filter (where copiou or loja)),
        jsonb_build_object('etapa', 'Baixaram o app', 'n', count(*) filter (where baixou))) from ses),
    'diario', (select coalesce(jsonb_agg(x order by x.dia desc), '[]') from (
        select date_trunc('day', criado at time zone 'America/Sao_Paulo')::date dia, count(distinct sessao) visitas,
               count(distinct sessao) filter (where tipo = 'radar') radar, count(*) filter (where tipo = 'copiar') comandos,
               count(*) filter (where tipo = 'download') downloads
        from e30 group by 1) x),
    'origens', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(utm_source, origem, '(direto)') origem, count(distinct sessao) visitas,
               round(100.0 * count(distinct sessao) filter (where tipo = 'radar') / nullif(count(distinct sessao), 0)) pct_radar,
               count(distinct sessao) filter (where tipo = 'download') baixaram
        from e30 group by 1 order by 2 desc limit 15) x),
    'usos', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(nullif(dados->>'uso', ''), 'geral') uso, count(distinct sessao) visitas
        from e30 where tipo = 'radar' group by 1 order by 2 desc limit 12) x),
    'hardware_site', (select coalesce(jsonb_agg(x), '[]') from (
        select dados->>'perfil' hardware, count(distinct sessao) visitas,
               count(distinct sessao) filter (where coalesce(dados->>'palpite', 'exemplo') <> 'exemplo') detectado
        from e30 where tipo in ('radar','calculadora') and dados ? 'perfil' group by 1 order by 2 desc limit 15) x),
    'modelos_copiados', (select coalesce(jsonb_agg(x), '[]') from (
        select regexp_replace(dados->>'comando', '^ollama (pull|run) ', '') modelo, count(*) copias
        from e30 where tipo = 'copiar' group by 1 order by 2 desc limit 15) x),
    'abas', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(dados->>'aba', aba) aba, count(distinct sessao) visitas
        from e30 where tipo in ('pagina','aba') group by 1 order by 2 desc limit 10) x),
    'idiomas', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(nullif(left(idioma, 2), ''), '?') idioma, count(*) visitas from ses group by 1 order by 2 desc limit 8) x),
    'downloads_origem', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(dados->>'origem', '?') origem, count(*) n from e30 where tipo = 'download' group by 1 order by 2 desc) x),
    'placas_comunidade', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(hardware->>'gpu', 'Sem placa (' || coalesce(hardware->>'ram_gb','?') || ' GB RAM)') placa,
               count(*) envios, count(distinct modelo) modelos
        from b group by 1 order by 2 desc limit 20) x),
    'modelos_comunidade', (select coalesce(jsonb_agg(x), '[]') from (
        select modelo, coalesce(hardware->>'gpu', 'Sem placa') placa, count(*) envios,
               round(avg((resultado->>'tps')::numeric), 1) tps_medio,
               round(avg((select avg((v->>'nota')::numeric) from jsonb_each(resultado->'papeis') e(k, v))), 1) nota_media
        from b group by 1, 2 order by 3 desc, 1 limit 40) x)
  ) into r;
  return r;
end $$;

-- Público: quantos resultados a comunidade já mandou e, para uma placa, a média de cada modelo medido nela.
create or replace function public.comunidade_resumo(p_gpu text default null)
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'envios', (select count(*) from privado.benchmarks),
    'maquinas', (select count(distinct hardware) from privado.benchmarks),
    'na_placa', (select coalesce(jsonb_agg(x), '[]') from (
        select modelo, count(*) envios, round(avg((resultado->>'tps')::numeric), 0) tps,
               round(avg((select avg((v->>'nota')::numeric) from jsonb_each(resultado->'papeis') e(k, v))), 0) nota
        from privado.benchmarks
        where p_gpu is not null and coalesce(hardware->>'gpu', 'cpu') = left(p_gpu, 120)
        group by 1 order by nota desc nulls last limit 8) x));
$$;
revoke all on function public.comunidade_resumo(text) from public;
grant execute on function public.comunidade_resumo(text) to anon, authenticated;
