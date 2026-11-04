-- Visões para analisar as métricas (só leitura por quem administra o banco; nada exposto na API).
create or replace view privado.v_diario as
select date_trunc('day', criado at time zone 'America/Sao_Paulo')::date as dia,
       count(distinct sessao) as visitas,
       count(distinct sessao) filter (where novo) as visitas_novas,
       count(*) filter (where tipo in ('pagina','aba')) as abas_vistas,
       count(*) filter (where tipo = 'copiar') as comandos_copiados,
       count(distinct sessao) filter (where tipo = 'copiar') as visitas_que_copiaram,
       count(*) filter (where tipo = 'download') as downloads,
       count(*) filter (where tipo = 'loja') as cliques_loja,
       count(*) filter (where tipo = 'lead') as emails,
       count(*) filter (where tipo = 'apoio') as abriu_apoio
from privado.eventos
where host not like '%vercel.app'
group by 1 order by 1 desc;

create or replace view privado.v_origens as
select coalesce(utm_source, origem, '(direto)') as origem, utm_medium, utm_campaign,
       count(distinct sessao) as visitas,
       count(distinct sessao) filter (where tipo = 'copiar') as copiaram,
       count(distinct sessao) filter (where tipo = 'download') as baixaram,
       count(distinct sessao) filter (where tipo = 'lead') as deixaram_email,
       round(100.0 * count(distinct sessao) filter (where tipo = 'copiar') / nullif(count(distinct sessao), 0), 1) as pct_copiaram
from privado.eventos
where host not like '%vercel.app'
group by 1, 2, 3 order by visitas desc;

create or replace view privado.v_hardware as
select dados->>'perfil' as hardware, count(distinct sessao) as visitas,
       count(distinct sessao) filter (where dados->>'palpite' is not null and dados->>'palpite' <> 'exemplo') as por_palpite
from privado.eventos
where tipo in ('radar','calculadora') and dados ? 'perfil' and host not like '%vercel.app'
group by 1 order by visitas desc;

create or replace view privado.v_modelos_copiados as
select regexp_replace(dados->>'comando', '^ollama (pull|run) ', '') as modelo, count(*) as copias, count(distinct sessao) as visitas
from privado.eventos
where tipo = 'copiar' and host not like '%vercel.app'
group by 1 order by copias desc;

create or replace view privado.v_abas as
select coalesce(dados->>'aba', aba) as aba, count(*) as vistas, count(distinct sessao) as visitas
from privado.eventos where tipo in ('pagina','aba') and host not like '%vercel.app'
group by 1 order by vistas desc;

revoke all on privado.v_diario, privado.v_origens, privado.v_hardware, privado.v_modelos_copiados, privado.v_abas from public, anon, authenticated;
