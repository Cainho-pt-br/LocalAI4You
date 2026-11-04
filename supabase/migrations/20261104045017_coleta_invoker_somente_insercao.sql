-- Funções rodam com as permissões de quem chama (SECURITY INVOKER). O papel anônimo só pode INSERIR nas três tabelas
-- (sem SELECT, UPDATE ou DELETE) e o schema "privado" não é exposto pela API: a única porta são as funções abaixo.
grant usage on schema privado to anon, authenticated;
grant insert on privado.eventos, privado.leads, privado.benchmarks to anon, authenticated;
alter table privado.eventos enable row level security;
alter table privado.leads enable row level security;
alter table privado.benchmarks enable row level security;
drop policy if exists inserir_eventos on privado.eventos;
drop policy if exists inserir_leads on privado.leads;
drop policy if exists inserir_benchmarks on privado.benchmarks;
create policy inserir_eventos on privado.eventos for insert to anon, authenticated with check (true);
create policy inserir_leads on privado.leads for insert to anon, authenticated with check (descadastrado = false);
create policy inserir_benchmarks on privado.benchmarks for insert to anon, authenticated with check (true);

alter function public.registrar_evento(text,text,text,boolean,text,jsonb,text,text,text,jsonb) security invoker;
alter function public.enviar_benchmark(jsonb) security invoker;

-- lead: sempre responde "ok" (não revela se o e-mail já estava na lista) e não precisa de SELECT
create or replace function public.registrar_lead(
  p_email text, p_consentimento text, p_interesse text default 'novidades', p_hardware text default null, p_origem text default null)
returns text language plpgsql security invoker set search_path = '' as $$
declare v_email text := lower(trim(p_email));
begin
  if v_email is null or length(v_email) > 254 or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]{2,}$' then
    raise exception 'e-mail inválido';
  end if;
  if p_consentimento is null or length(p_consentimento) < 10 or length(p_consentimento) > 600 then
    raise exception 'consentimento ausente';
  end if;
  if coalesce(p_interesse,'novidades') not in ('novidades','alerta-hardware') then
    raise exception 'interesse inválido';
  end if;
  begin
    insert into privado.leads (email, interesse, hardware, origem, consentimento)
    values (v_email, coalesce(p_interesse,'novidades'), left(p_hardware, 120), left(p_origem, 60), p_consentimento);
  exception when unique_violation then
    null;
  end;
  return 'ok';
end $$;
revoke all on function public.registrar_lead(text,text,text,text,text) from public;
grant execute on function public.registrar_lead(text,text,text,text,text) to anon, authenticated;
