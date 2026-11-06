-- Painel interno: só números somados (nada individual), e só com a senha guardada em privado.painel_acesso.
create table if not exists privado.painel_acesso (senha text not null);
revoke all on privado.painel_acesso from public, anon, authenticated;

create or replace function public.painel_resumo(p_senha text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare r jsonb;
begin
  if p_senha is null or not exists (select 1 from privado.painel_acesso where senha = p_senha) then
    perform pg_sleep(1); raise exception 'senha incorreta';
  end if;
  with ev as (select * from privado.eventos where host not like '%-projects.vercel.app' and host not like 'localhost%'),
       b as (select * from privado.benchmarks)
  select jsonb_build_object(
    'gerado', now(),
    'totais', (select jsonb_build_object(
        'visitas_30d', (select count(distinct sessao) from ev where criado > now() - interval '30 days'),
        'visitas_7d', (select count(distinct sessao) from ev where criado > now() - interval '7 days'),
        'downloads_30d', (select count(*) from ev where tipo = 'download' and criado > now() - interval '30 days'),
        'comandos_30d', (select count(*) from ev where tipo = 'copiar' and criado > now() - interval '30 days'),
        'cliques_loja_30d', (select count(*) from ev where tipo = 'loja' and criado > now() - interval '30 days'),
        'benchmarks', (select count(*) from b),
        'benchmarks_7d', (select count(*) from b where criado > now() - interval '7 days'),
        'maquinas', (select count(distinct hardware) from b))),
    'diario', (select coalesce(jsonb_agg(x order by x.dia desc), '[]') from (
        select date_trunc('day', criado at time zone 'America/Sao_Paulo')::date dia, count(distinct sessao) visitas,
               count(*) filter (where tipo = 'download') downloads, count(*) filter (where tipo = 'copiar') comandos
        from ev where criado > now() - interval '30 days' group by 1) x),
    'origens', (select coalesce(jsonb_agg(x), '[]') from (
        select coalesce(utm_source, origem, '(direto)') origem, count(distinct sessao) visitas,
               count(distinct sessao) filter (where tipo = 'download') baixaram
        from ev where criado > now() - interval '30 days' group by 1 order by 2 desc limit 15) x),
    'hardware_site', (select coalesce(jsonb_agg(x), '[]') from (
        select dados->>'perfil' hardware, count(distinct sessao) visitas
        from ev where tipo in ('radar','calculadora') and dados ? 'perfil' and criado > now() - interval '30 days'
        group by 1 order by 2 desc limit 15) x),
    'modelos_copiados', (select coalesce(jsonb_agg(x), '[]') from (
        select regexp_replace(dados->>'comando', '^ollama (pull|run) ', '') modelo, count(*) copias
        from ev where tipo = 'copiar' and criado > now() - interval '30 days' group by 1 order by 2 desc limit 15) x),
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
revoke all on function public.painel_resumo(text) from public;
grant execute on function public.painel_resumo(text) to anon, authenticated;
