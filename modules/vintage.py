import datetime
import hashlib
import json
import math
import os
import re
import time

import redis
from flask import current_app, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import bindparam, text

from modules.extensions import db
from modules.views import views, debug_log

@views.route('/vintage-data', methods=['GET'])
def vintage():
	default_start_date = ''
	default_end_date = ''
	try:
		date_row = db.session.execute(text(
			'SELECT MIN("EVENT_DATE") AS min_event_date, MAX("EVENT_DATE") AS max_event_date '
			'FROM "[vapi].EVENTS"'
		)).first()
		if date_row:
			min_date = date_row[0]
			max_date = date_row[1]
			default_start_date = (
				min_date.strftime('%Y-%m-%d')
				if isinstance(min_date, (datetime.date, datetime.datetime))
				else str(min_date)[:10] if min_date is not None else ''
			)
			default_end_date = (
				max_date.strftime('%Y-%m-%d')
				if isinstance(max_date, (datetime.date, datetime.datetime))
				else str(max_date)[:10] if max_date is not None else ''
			)
	except Exception as e:
		debug_log(f'Error loading vintage default dates: {e}')

	return render_template(
		'vintage.html',
		user=current_user,
		vintage_date1=default_start_date,
		vintage_date2=default_end_date,
	)

@views.route('/vintage-data/api-documentation', methods=['GET'])
def vintage_api_documentation():
	return render_template('vintage-api.html', user=current_user)

@views.route('/vintage-data/data-dictionary', methods=['GET'])
def vintage_data_dictionary():
	return render_template('vintage-datadict.html', user=current_user)

VINTAGE_FORCE_UPPER_TERMS = {'BUG', 'DRS', 'PO', 'NA', 'UB'}
VINTAGE_RESPONSE_CACHE_FRESH_TTL_SECONDS = int(os.environ.get('VINTAGE_RESPONSE_CACHE_FRESH_TTL_SECONDS', str(24 * 60 * 60)))
VINTAGE_RESPONSE_CACHE_STALE_WINDOW_SECONDS = int(os.environ.get('VINTAGE_RESPONSE_CACHE_STALE_WINDOW_SECONDS', str(21 * 24 * 60 * 60)))
VINTAGE_RESPONSE_CACHE_MAX_ENTRIES = int(os.environ.get('VINTAGE_RESPONSE_CACHE_MAX_ENTRIES', '512'))
_vintage_response_redis_client = None
_VINTAGE_CACHE_NAMESPACE_KEY = 'vintage:response:namespace_version'

def _format_vintage_label_value(value):
	if value is None:
		return ''
	raw = str(value).strip()
	if not raw:
		return ''
	parts = re.split(r'(\W+)', raw)
	formatted_parts = []
	for part in parts:
		if not part:
			continue
		upper_part = part.upper()
		if upper_part in VINTAGE_FORCE_UPPER_TERMS:
			formatted_parts.append(upper_part)
		elif part.isalpha():
			formatted_parts.append(part[0].upper() + part[1:].lower())
		else:
			formatted_parts.append(part)
	return ''.join(formatted_parts)

def _normalize_vintage_cache_key_value(value):
	"""Normalize values so cache keys are deterministic."""
	if value is None:
		return None
	if isinstance(value, (datetime.date, datetime.datetime)):
		return value.strftime('%Y-%m-%d')
	if isinstance(value, dict):
		return {
			str(k): _normalize_vintage_cache_key_value(v)
			for k, v in sorted(value.items(), key=lambda item: str(item[0]))
		}
	if isinstance(value, (list, tuple, set)):
		return [_normalize_vintage_cache_key_value(v) for v in value]
	return str(value).strip() if isinstance(value, str) else value

def _build_vintage_response_cache_key(endpoint_name, payload):
	"""Build a stable cache key for vintage response payloads."""
	normalized_payload = _normalize_vintage_cache_key_value(payload)
	return json.dumps(
		{
			'endpoint': str(endpoint_name or '').strip().lower(),
			'payload': normalized_payload,
		},
		sort_keys=True,
		separators=(',', ':'),
	)

def _get_vintage_response_redis_client():
	"""Initialize Redis client for vintage response caching."""
	global _vintage_response_redis_client
	if _vintage_response_redis_client is not None:
		return _vintage_response_redis_client

	redis_url = (os.environ.get('CELERY_RESULT_BACKEND') or '').strip()
	if not redis_url:
		try:
			redis_url = str(current_app.config.get('CELERY_RESULT_BACKEND') or '').strip()
		except Exception:
			redis_url = ''
	if not redis_url:
		return None
	if not (redis_url.lower().startswith('redis://') or redis_url.lower().startswith('rediss://')):
		return None

	try:
		redis_kwargs = {}
		if redis_url.lower().startswith('rediss://'):
			redis_kwargs['ssl_cert_reqs'] = 'required'
		_vintage_response_redis_client = redis.Redis.from_url(redis_url, **redis_kwargs)
		_vintage_response_redis_client.ping()
		return _vintage_response_redis_client
	except Exception as error:
		debug_log(f'Vintage response cache Redis initialization failed: {error}')
		return None

def _decode_redis_text(value):
	if isinstance(value, bytes):
		try:
			return value.decode('utf-8')
		except Exception:
			return ''
	return str(value or '')

def _get_vintage_cache_namespace_value(redis_client):
	"""Get or initialize namespace version used for global invalidation."""
	try:
		value = _decode_redis_text(redis_client.get(_VINTAGE_CACHE_NAMESPACE_KEY)).strip()
		if not value:
			redis_client.set(_VINTAGE_CACHE_NAMESPACE_KEY, '1')
			return '1'
		return value
	except Exception:
		return '1'

def _vintage_cache_storage_key(cache_key, namespace_value):
	key_digest = hashlib.sha256(str(cache_key or '').encode('utf-8')).hexdigest()
	return f'vintage:response:{namespace_value}:{key_digest}'

def _vintage_cache_index_key(namespace_value):
	return f'vintage:response:index:{namespace_value}'

def _get_cached_vintage_response(cache_key):
	"""Return cached payload when still inside fresh+stale window."""
	if not cache_key:
		return None

	redis_client = _get_vintage_response_redis_client()
	if redis_client is None:
		return None

	try:
		now = time.time()
		namespace_value = _get_vintage_cache_namespace_value(redis_client)
		redis_key = _vintage_cache_storage_key(cache_key, namespace_value)
		index_key = _vintage_cache_index_key(namespace_value)
		raw_entry = redis_client.get(redis_key)
		if not raw_entry:
			return None
		entry = json.loads(_decode_redis_text(raw_entry))
		if float((entry or {}).get('stale_until') or 0) <= now:
			redis_client.zrem(index_key, redis_key)
			redis_client.delete(redis_key)
			return None
		# LRU touch: successful reads update recency score.
		redis_client.zadd(index_key, {redis_key: now})
		return (entry or {}).get('payload')
	except Exception as error:
		debug_log(f'Vintage response cache Redis read failed: {error}')
		return None

def _set_cached_vintage_response(cache_key, payload):
	"""Store payload with a long fresh TTL and stale-serve window."""
	if not cache_key or payload is None:
		return

	redis_client = _get_vintage_response_redis_client()
	if redis_client is None:
		return

	try:
		now = time.time()
		fresh_ttl = max(1, int(VINTAGE_RESPONSE_CACHE_FRESH_TTL_SECONDS or (24 * 60 * 60)))
		stale_window = max(1, int(VINTAGE_RESPONSE_CACHE_STALE_WINDOW_SECONDS or (21 * 24 * 60 * 60)))
		total_ttl = max(1, fresh_ttl + stale_window)
		namespace_value = _get_vintage_cache_namespace_value(redis_client)
		redis_key = _vintage_cache_storage_key(cache_key, namespace_value)

		entry = {
			'payload': payload,
			'stored_at': now,
			'fresh_until': now + fresh_ttl,
			'stale_until': now + fresh_ttl + stale_window,
		}
		serialized = json.dumps(entry, separators=(',', ':'), ensure_ascii=True)
		index_key = _vintage_cache_index_key(namespace_value)

		pipe = redis_client.pipeline()
		pipe.setex(redis_key, total_ttl, serialized)
		pipe.zadd(index_key, {redis_key: now})
		pipe.zcard(index_key)
		_, _, total_indexed = pipe.execute()

		max_entries = max(1, int(VINTAGE_RESPONSE_CACHE_MAX_ENTRIES or 128))
		extra_entries = int(total_indexed or 0) - max_entries
		if extra_entries > 0:
			oldest_keys = redis_client.zrange(index_key, 0, extra_entries - 1)
			if oldest_keys:
				trim_pipe = redis_client.pipeline()
				trim_pipe.delete(*oldest_keys)
				trim_pipe.zrem(index_key, *oldest_keys)
				trim_pipe.execute()
	except Exception as error:
		debug_log(f'Vintage response cache Redis write failed: {error}')

def _cache_and_return_vintage_payload(cache_key, payload):
	"""Cache and return plain JSON payload."""
	_set_cached_vintage_response(cache_key, payload)
	return jsonify(payload)

def _cache_and_return_vintage_dashboard_data(cache_key, data):
	"""Cache and return vintage dashboard success payload."""
	_set_cached_vintage_response(cache_key, data)
	return jsonify({'success': True, 'data': data})

def _build_vintage_generate_cache_payload(dashboard_type, filters):
	"""Build canonical cache payload for generate route without changing semantics."""
	raw_filters = filters or {}

	start_date = str(raw_filters.get('startDate') or '').strip()
	end_date = str(raw_filters.get('endDate') or '').strip()
	event_type = str(raw_filters.get('eventType') or '').strip().upper()
	archetype = str(raw_filters.get('archetype') or '').strip().upper()
	subarchetype = str(raw_filters.get('subarchetype') or '').strip().upper()
	player_filter = str(raw_filters.get('player') or '').strip().upper()
	event_id = str(raw_filters.get('eventId') or '').strip()

	canonical_filters = {}
	if start_date:
		canonical_filters['startDate'] = start_date
	if end_date:
		canonical_filters['endDate'] = end_date
	if event_type:
		canonical_filters['eventType'] = event_type
	if archetype:
		canonical_filters['archetype'] = archetype
	if subarchetype:
		canonical_filters['subarchetype'] = subarchetype
	if player_filter:
		canonical_filters['player'] = player_filter
	if event_id:
		canonical_filters['eventId'] = event_id

	return {
		'dashboard_type': str(dashboard_type or '').strip().lower(),
		'filters': canonical_filters,
	}

def clear_vintage_response_cache():
	"""Clear vintage response cache and return simple stats."""
	redis_client = _get_vintage_response_redis_client()
	if redis_client is None:
		return {
			'cleared_entries': 0,
			'cleared_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
			'used_redis': False,
		}

	namespace_before = ''
	namespace_after = ''
	cleared_entries = 0
	try:
		namespace_before = _get_vintage_cache_namespace_value(redis_client)
		pattern = f'vintage:response:{namespace_before}:*'
		delete_batch = []
		for key in redis_client.scan_iter(match=pattern, count=1000):
			delete_batch.append(key)
			cleared_entries += 1
			if len(delete_batch) >= 500:
				redis_client.delete(*delete_batch)
				delete_batch = []
		if delete_batch:
			redis_client.delete(*delete_batch)
		redis_client.delete(_vintage_cache_index_key(namespace_before))

		try:
			current_namespace = int(namespace_before or '1')
		except ValueError:
			current_namespace = 1
		namespace_after = str(max(1, current_namespace + 1))
		redis_client.set(_VINTAGE_CACHE_NAMESPACE_KEY, namespace_after)
	except Exception as error:
		debug_log(f'Vintage response cache Redis clear failed: {error}')

	return {
		'cleared_entries': int(cleared_entries),
		'cleared_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
		'used_redis': True,
		'redis_namespace_before': namespace_before,
		'redis_namespace_after': namespace_after,
	}

@views.route('/api/vintage/filter-options', methods=['GET'])
def vintage_filter_options():
	cache_key = _build_vintage_response_cache_key('vintage-filter-options', {'v': 1})
	cached_payload = _get_cached_vintage_response(cache_key)
	if cached_payload is not None:
		return jsonify(cached_payload)

	filter_options_dict = {
		'Date1': '',
		'Date2': '',
		'EventId': [],
		'EventType': [],
		'Archetype': [],
		'Subarchetype': [],
		'Player': [],
	}

	def _normalize_date_value(value):
		if value is None:
			return ''
		if isinstance(value, (datetime.date, datetime.datetime)):
			return value.strftime('%Y-%m-%d')
		text_value = str(value).strip()
		if not text_value:
			return ''
		return text_value[:10]

	try:
		date_row = db.session.execute(text(
			'SELECT MIN("EVENT_DATE") AS min_event_date, MAX("EVENT_DATE") AS max_event_date '
			'FROM "[vapi].EVENTS"'
		)).first()
		if date_row:
			filter_options_dict['Date1'] = _normalize_date_value(date_row[0])
			filter_options_dict['Date2'] = _normalize_date_value(date_row[1])

		event_id_rows = db.session.execute(text(
			'SELECT DISTINCT e."EVENT_ID" '
			'FROM "[vapi].EVENTS" e '
			'WHERE e."EVENT_ID" IS NOT NULL '
			'ORDER BY e."EVENT_ID" DESC'
		)).all()
		filter_options_dict['EventId'] = [
			str(row[0]).strip() for row in event_id_rows if row and row[0] is not None and str(row[0]).strip()
		]

		event_type_rows = db.session.execute(text(
			'SELECT DISTINCT vet."EVENT_TYPE" '
			'FROM "[vapi].EVENTS" e '
			'JOIN "[vapi].VALID_EVENT_TYPES" vet ON e."EVENT_TYPE_ID" = vet."EVENT_TYPE_ID" '
			'WHERE vet."EVENT_TYPE" IS NOT NULL '
			'ORDER BY vet."EVENT_TYPE"'
		)).all()
		filter_options_dict['EventType'] = [
			_format_vintage_label_value(row[0]) for row in event_type_rows if row and row[0]
		]

		archetype_rows = db.session.execute(text(
			'SELECT DISTINCT vd."ARCHETYPE" '
			'FROM "[vapi].MATCHES" m '
			'JOIN "[vapi].VALID_DECKS" vd ON m."P1_DECK_ID" = vd."DECK_ID" '
			'WHERE vd."ARCHETYPE" IS NOT NULL '
			'ORDER BY vd."ARCHETYPE"'
		)).all()
		filter_options_dict['Archetype'] = [
			_format_vintage_label_value(row[0])
			for row in archetype_rows
			if row and row[0] and str(row[0]).strip().upper() != 'NA'
		]

		subarchetype_rows = db.session.execute(text(
			'SELECT DISTINCT vd."SUBARCHETYPE" '
			'FROM "[vapi].MATCHES" m '
			'JOIN "[vapi].VALID_DECKS" vd ON m."P1_DECK_ID" = vd."DECK_ID" '
			'WHERE vd."SUBARCHETYPE" IS NOT NULL '
			'ORDER BY vd."SUBARCHETYPE"'
		)).all()
		filter_options_dict['Subarchetype'] = [
			_format_vintage_label_value(row[0])
			for row in subarchetype_rows
			if row and row[0] and str(row[0]).strip().upper() not in {'NA', 'NO SHOW'}
		]

		player_rows = db.session.execute(text(
			'SELECT DISTINCT m."P1" '
			'FROM "[vapi].MATCHES" m '
			'WHERE m."P1" IS NOT NULL '
			'ORDER BY m."P1"'
		)).all()
		filter_options_dict['Player'] = [
			str(row[0]).strip() for row in player_rows if row and row[0] and str(row[0]).strip()
		]

	except Exception as error:
		debug_log(f'Error loading vintage filter options: {error}')
		return jsonify({'error': 'Failed to load vintage filter options'}), 500

	return _cache_and_return_vintage_payload(cache_key, filter_options_dict)

@views.route('/api/vintage/filtered-options', methods=['POST'])
def vintage_filtered_options():
	payload = request.get_json() or {}
	filters = payload.get('filters') or {}

	filter_options_dict = {
		'Date1': '',
		'Date2': '',
		'EventId': [],
		'EventType': [],
		'Archetype': [],
		'Subarchetype': [],
		'Player': [],
	}

	try:
		event_id = str(filters.get('eventId') or '').strip()
		event_type = str(filters.get('eventType') or '').strip()
		archetype = str(filters.get('archetype') or '').strip()
		subarchetype = str(filters.get('subarchetype') or '').strip()
		player_filter = str(filters.get('player') or '').strip()

		sql_filters = []
		params = {}
		if event_id:
			sql_filters.append('CAST(m."EVENT_ID" AS VARCHAR) = :event_id')
			params['event_id'] = event_id
		if event_type:
			sql_filters.append('UPPER(vet."EVENT_TYPE") = :event_type')
			params['event_type'] = event_type.upper()
		if archetype:
			sql_filters.append('UPPER(vd1."ARCHETYPE") = :archetype')
			params['archetype'] = archetype.upper()
		if subarchetype:
			sql_filters.append('UPPER(vd1."SUBARCHETYPE") = :subarchetype')
			params['subarchetype'] = subarchetype.upper()
		if player_filter:
			sql_filters.append('UPPER(m."P1") = :player_filter')
			params['player_filter'] = player_filter.upper()

		where_clause = f'WHERE {" AND ".join(sql_filters)}' if sql_filters else ''
		filtered_rows_sql = text(
			'SELECT '
			'  CAST(m."EVENT_ID" AS VARCHAR) AS event_id, '
			'  e."EVENT_DATE" AS event_date, '
			'  vet."EVENT_TYPE" AS event_type, '
			'  vd1."ARCHETYPE" AS archetype, '
			'  vd1."SUBARCHETYPE" AS subarchetype, '
			'  m."P1" AS player '
			'FROM "[vapi].MATCHES" m '
			'LEFT JOIN "[vapi].EVENTS" e ON m."EVENT_ID" = e."EVENT_ID" '
			'LEFT JOIN "[vapi].VALID_EVENT_TYPES" vet ON e."EVENT_TYPE_ID" = vet."EVENT_TYPE_ID" '
			'LEFT JOIN "[vapi].VALID_DECKS" vd1 ON m."P1_DECK_ID" = vd1."DECK_ID" '
			f'{where_clause}'
		)
		filtered_rows = [dict(r._mapping) for r in db.session.execute(filtered_rows_sql, params).all()]

		event_ids = {
			str(row.get('event_id') or '').strip()
			for row in filtered_rows
			if str(row.get('event_id') or '').strip()
		}
		filter_options_dict['EventId'] = sorted(
			event_ids,
			key=lambda value: (0, int(value)) if value.isdigit() else (1, value.lower()),
			reverse=True
		)

		event_types = {
			_format_vintage_label_value(row.get('event_type'))
			for row in filtered_rows
			if row.get('event_type')
		}
		filter_options_dict['EventType'] = sorted(
			(value for value in event_types if value),
			key=lambda value: value.lower()
		)

		archetypes = {
			_format_vintage_label_value(row.get('archetype'))
			for row in filtered_rows
			if row.get('archetype') and str(row.get('archetype')).strip().upper() != 'NA'
		}
		filter_options_dict['Archetype'] = sorted(
			(value for value in archetypes if value),
			key=lambda value: value.lower()
		)

		subarchetypes = {
			_format_vintage_label_value(row.get('subarchetype'))
			for row in filtered_rows
			if row.get('subarchetype') and str(row.get('subarchetype')).strip().upper() not in {'NA', 'NO SHOW'}
		}
		filter_options_dict['Subarchetype'] = sorted(
			(value for value in subarchetypes if value),
			key=lambda value: value.lower()
		)

		players = {
			str(row.get('player') or '').strip()
			for row in filtered_rows
			if str(row.get('player') or '').strip()
		}
		filter_options_dict['Player'] = sorted(players, key=lambda value: value.lower())

		date_row = db.session.execute(text(
			'SELECT MIN("EVENT_DATE") AS min_event_date, MAX("EVENT_DATE") AS max_event_date '
			'FROM "[vapi].EVENTS"'
		)).first()
		if date_row:
			min_date = date_row[0]
			max_date = date_row[1]
			filter_options_dict['Date1'] = (
				min_date.strftime('%Y-%m-%d')
				if isinstance(min_date, (datetime.date, datetime.datetime))
				else str(min_date)[:10] if min_date is not None else ''
			)
			filter_options_dict['Date2'] = (
				max_date.strftime('%Y-%m-%d')
				if isinstance(max_date, (datetime.date, datetime.datetime))
				else str(max_date)[:10] if max_date is not None else ''
			)

		return jsonify(filter_options_dict)

	except Exception as error:
		debug_log(f'Error loading vintage filtered options: {error}')
		return jsonify({'error': 'Failed to load vintage filtered options'}), 500

def _compute_vintage_metagame_table(rows, key_field, opp_key_field, excluded_values=None):
	grouped = {}
	all_players = set()
	excluded = {str(v).strip().upper() for v in (excluded_values or set())}

	for row in rows:
		group_key = (row.get(key_field) or '').strip()
		if not group_key:
			continue
		if group_key.upper() in excluded:
			continue

		event_id = row.get('EVENT_ID')
		p1_player = row.get('P1')
		match_id = row.get('MATCH_ID')
		match_winner = (row.get('MATCH_WINNER') or '').strip().upper()
		opp_group_key = (row.get(opp_key_field) or '').strip()

		if group_key not in grouped:
			grouped[group_key] = {
				'players': set(),
				'matches': set(),
				'match_wins': 0,
				'match_losses': 0,
				'no_mirror_matches': set(),
				'no_mirror_wins': 0,
				'no_mirror_losses': 0,
			}

		metrics = grouped[group_key]

		if event_id and p1_player:
			player_tuple = (str(event_id), str(p1_player))
			metrics['players'].add(player_tuple)
			all_players.add(player_tuple)

		if match_id and p1_player:
			match_tuple = (str(match_id), str(p1_player))
			metrics['matches'].add(match_tuple)

			if match_winner == 'P1':
				metrics['match_wins'] += 1
			elif match_winner == 'P2':
				metrics['match_losses'] += 1

			is_no_mirror = bool(opp_group_key) and (group_key.upper() != opp_group_key.upper())
			if is_no_mirror:
				metrics['no_mirror_matches'].add(match_tuple)
				if match_winner == 'P1':
					metrics['no_mirror_wins'] += 1
				elif match_winner == 'P2':
					metrics['no_mirror_losses'] += 1

	total_players_all = len(all_players)
	result_rows = []
	for group_name, metrics in grouped.items():
		players = len(metrics['players'])
		total_matches = len(metrics['matches'])
		match_wins = metrics['match_wins']
		match_losses = metrics['match_losses']

		mwp_overall = (match_wins / (match_wins + match_losses)) if (match_wins + match_losses) > 0 else 0.0
		ci_95 = 1.96 * math.sqrt((mwp_overall * (1 - mwp_overall)) / total_matches) if total_matches > 0 else 0.0

		no_mirror_matches = len(metrics['no_mirror_matches'])
		no_mirror_wins = metrics['no_mirror_wins']
		no_mirror_losses = metrics['no_mirror_losses']
		mwp_no_mirrors = (no_mirror_wins / (no_mirror_wins + no_mirror_losses)) if (no_mirror_wins + no_mirror_losses) > 0 else 0.0
		ci_95_no_mirrors = 1.96 * math.sqrt((mwp_no_mirrors * (1 - mwp_no_mirrors)) / no_mirror_matches) if no_mirror_matches > 0 else 0.0

		meta_pct = (players / total_players_all) if total_players_all > 0 else 0.0

		result_rows.append({
			'name': _format_vintage_label_value(group_name),
			'players': players,
			'meta_pct': meta_pct,
			'mwp_overall': mwp_overall,
			'ci_95': ci_95,
			'mwp_no_mirrors': mwp_no_mirrors,
			'ci_95_no_mirrors': ci_95_no_mirrors,
			'total_matches': total_matches,
			'total_matches_no_mirrors': no_mirror_matches,
		})

	result_rows.sort(key=lambda r: (-r['players'], r['name'].lower()))
	return result_rows

def _compute_vintage_matchup_graph_series(rows, opp_key_field, excluded_values=None):
	grouped = {}
	excluded = {str(v).strip().upper() for v in (excluded_values or set())}

	for row in rows:
		opponent_raw = (row.get(opp_key_field) or '').strip()
		if not opponent_raw:
			continue
		if opponent_raw.upper() in excluded:
			continue

		opponent = _format_vintage_label_value(opponent_raw)
		if not opponent:
			continue

		match_id = str(row.get('MATCH_ID') or '').strip()
		player = str(row.get('P1') or '').strip()
		match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
		if not match_id or not player:
			continue

		metrics = grouped.setdefault(
			opponent,
			{
				'matches': set(),
				'wins': 0,
				'losses': 0,
			}
		)
		match_key = (match_id, player)
		if match_key in metrics['matches']:
			continue
		metrics['matches'].add(match_key)

		if match_winner == 'P1':
			metrics['wins'] += 1
		elif match_winner == 'P2':
			metrics['losses'] += 1

	result_rows = []
	for opponent, metrics in grouped.items():
		total_matches = len(metrics['matches'])
		wins = int(metrics['wins'] or 0)
		losses = int(metrics['losses'] or 0)
		match_win_pct = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
		ci_95 = 1.96 * math.sqrt((match_win_pct * (1 - match_win_pct)) / total_matches) if total_matches > 0 else 0.0
		ci_high = max(0.0, min(1.0, match_win_pct + ci_95))
		ci_low = max(0.0, min(1.0, match_win_pct - ci_95))

		result_rows.append({
			'name': opponent,
			'total_matches': total_matches,
			'match_win_pct': match_win_pct,
			'ci_95': ci_95,
			'ci_high': ci_high,
			'ci_low': ci_low,
		})

	result_rows.sort(key=lambda r: (-r['total_matches'], -r['match_win_pct'], r['name'].lower()))
	return result_rows

@views.route('/api/vintage/dashboard/generate', methods=['POST'])
def api_vintage_dashboard_generate():
	try:
		payload = request.get_json() or {}
		dashboard_type = (payload.get('dashboard_type') or '').strip().lower()
		filters = payload.get('filters') or {}

		if dashboard_type not in {'metagame-breakdown', 'event-explorer', 'player-leaderboard', 'matchup-heatmap', 'matchup-graph'}:
			return jsonify({'success': False, 'error': f'Unsupported dashboard type: {dashboard_type}'}), 400

		cache_key = _build_vintage_response_cache_key(
			'vintage-dashboard-generate',
			_build_vintage_generate_cache_payload(dashboard_type, filters)
		)
		cached_payload = _get_cached_vintage_response(cache_key)
		if cached_payload is not None:
			return jsonify({'success': True, 'data': cached_payload})

		sql_filters = []
		params = {}

		start_date = (filters.get('startDate') or '').strip()
		end_date = (filters.get('endDate') or '').strip()
		event_type = (filters.get('eventType') or '').strip()
		archetype = (filters.get('archetype') or '').strip()
		subarchetype = (filters.get('subarchetype') or '').strip()
		player_filter = (filters.get('player') or '').strip()
		selected_event_id = str(filters.get('eventId') or '').strip()

		if start_date:
			sql_filters.append('e."EVENT_DATE" >= :start_date')
			params['start_date'] = start_date
		if end_date:
			sql_filters.append('e."EVENT_DATE" <= :end_date')
			params['end_date'] = end_date
		if event_type:
			sql_filters.append('UPPER(vet."EVENT_TYPE") = :event_type')
			params['event_type'] = event_type.upper()
		if archetype:
			sql_filters.append('UPPER(vd1."ARCHETYPE") = :archetype')
			params['archetype'] = archetype.upper()
		if subarchetype:
			sql_filters.append('UPPER(vd1."SUBARCHETYPE") = :subarchetype')
			params['subarchetype'] = subarchetype.upper()
		if player_filter:
			sql_filters.append('UPPER(m."P1") = :player_filter')
			params['player_filter'] = player_filter.upper()
		if selected_event_id:
			sql_filters.append('CAST(m."EVENT_ID" AS VARCHAR) = :selected_event_id')
			params['selected_event_id'] = selected_event_id

		where_clause = ''
		if sql_filters:
			where_clause = 'WHERE ' + ' AND '.join(sql_filters)

		matches_sql = text(
			'SELECT '
			'  m."MATCH_ID", '
			'  m."EVENT_ID", '
			'  m."P1", '
			'  m."MATCH_WINNER", '
			'  vd1."ARCHETYPE" AS p1_archetype, '
			'  vd1."SUBARCHETYPE" AS p1_subarchetype, '
			'  vd2."ARCHETYPE" AS p2_archetype, '
			'  vd2."SUBARCHETYPE" AS p2_subarchetype '
			'FROM "[vapi].MATCHES" m '
			'LEFT JOIN "[vapi].VALID_DECKS" vd1 ON m."P1_DECK_ID" = vd1."DECK_ID" '
			'LEFT JOIN "[vapi].VALID_DECKS" vd2 ON m."P2_DECK_ID" = vd2."DECK_ID" '
			'LEFT JOIN "[vapi].EVENTS" e ON m."EVENT_ID" = e."EVENT_ID" '
			'LEFT JOIN "[vapi].VALID_EVENT_TYPES" vet ON e."EVENT_TYPE_ID" = vet."EVENT_TYPE_ID" '
			f'{where_clause}'
		)

		if dashboard_type == 'metagame-breakdown':
			rows = [dict(r._mapping) for r in db.session.execute(matches_sql, params).all()]
			unique_players = len({
				(str(row.get('P1') or '').strip())
				for row in rows
				if str(row.get('P1') or '').strip()
			})

			archetype_rows = _compute_vintage_metagame_table(
				rows=rows,
				key_field='p1_archetype',
				opp_key_field='p2_archetype',
				excluded_values={'NA'},
			)
			subarchetype_rows = _compute_vintage_metagame_table(
				rows=rows,
				key_field='p1_subarchetype',
				opp_key_field='p2_subarchetype',
				excluded_values={'NA', 'NO SHOW'},
			)

			return _cache_and_return_vintage_dashboard_data(
				cache_key,
				{
					'unique_players': unique_players,
					'archetype_rows': archetype_rows,
					'subarchetype_rows': subarchetype_rows,
				}
			)

		if dashboard_type == 'matchup-graph':
			rows = [dict(r._mapping) for r in db.session.execute(matches_sql, params).all()]
			unique_players = len({
				(str(row.get('P1') or '').strip())
				for row in rows
				if str(row.get('P1') or '').strip()
			})
			seen_match_players = set()
			match_wins = 0
			match_losses = 0
			for row in rows:
				match_id = str(row.get('MATCH_ID') or '').strip()
				player = str(row.get('P1') or '').strip()
				match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
				if not match_id or not player:
					continue
				match_key = (match_id, player)
				if match_key in seen_match_players:
					continue
				seen_match_players.add(match_key)
				if match_winner == 'P1':
					match_wins += 1
				elif match_winner == 'P2':
					match_losses += 1
			match_win_pct = (match_wins / (match_wins + match_losses)) if (match_wins + match_losses) > 0 else 0.0

			opponent_archetype_rows = _compute_vintage_matchup_graph_series(
				rows=rows,
				opp_key_field='p2_archetype',
				excluded_values={'NA'},
			)
			opponent_subarchetype_rows = _compute_vintage_matchup_graph_series(
				rows=rows,
				opp_key_field='p2_subarchetype',
				excluded_values={'NA', 'NO SHOW'},
			)

			return _cache_and_return_vintage_dashboard_data(
				cache_key,
				{
					'unique_players': unique_players,
					'match_win_pct': match_win_pct,
					'opponent_archetype_rows': opponent_archetype_rows,
					'opponent_subarchetype_rows': opponent_subarchetype_rows,
				}
			)

		if dashboard_type == 'player-leaderboard':
			player_rows_sql = text(
				'SELECT '
				'  m."EVENT_ID", '
				'  m."MATCH_ID", '
				'  m."P1", '
				'  m."P2", '
				'  m."MATCH_WINNER", '
				'  e."EVENT_DATE", '
				'  vet."EVENT_TYPE", '
				'  vd1."SUBARCHETYPE" AS p1_subarchetype '
				'FROM "[vapi].MATCHES" m '
				'LEFT JOIN "[vapi].EVENTS" e ON m."EVENT_ID" = e."EVENT_ID" '
				'LEFT JOIN "[vapi].VALID_EVENT_TYPES" vet ON e."EVENT_TYPE_ID" = vet."EVENT_TYPE_ID" '
				'LEFT JOIN "[vapi].VALID_DECKS" vd1 ON m."P1_DECK_ID" = vd1."DECK_ID" '
				f'{where_clause}'
			)
			player_rows = [dict(r._mapping) for r in db.session.execute(player_rows_sql, params).all()]

			per_player = {}
			relevant_event_ids = set()
			relevant_player_events = set()
			for row in player_rows:
				player_name = str(row.get('P1') or '').strip()
				event_id = str(row.get('EVENT_ID') or '').strip()
				match_id = str(row.get('MATCH_ID') or '').strip()
				match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
				if not player_name:
					continue

				metrics = per_player.setdefault(
					player_name,
					{
						'matches': set(),
						'events': set(),
						'wins': 0,
						'losses': 0,
					}
				)
				if event_id:
					metrics['events'].add(event_id)
					relevant_event_ids.add(event_id)
					relevant_player_events.add((event_id, player_name.upper()))
				if match_id:
					metrics['matches'].add((match_id, player_name))
				if match_winner == 'P1':
					metrics['wins'] += 1
				elif match_winner == 'P2':
					metrics['losses'] += 1

			standings_by_player = {}
			if relevant_event_ids:
				standings_sql = text(
					'SELECT es."EVENT_ID", es."P1", es."EVENT_RANK" '
					'FROM "[vapi].EVENT_STANDINGS" es '
					'WHERE es."EVENT_ID" IN :event_ids'
				).bindparams(bindparam('event_ids', expanding=True))
				standings_rows = [dict(r._mapping) for r in db.session.execute(standings_sql, {'event_ids': list(relevant_event_ids)}).all()]

				for standing in standings_rows:
					player_name = str(standing.get('P1') or '').strip()
					event_id = str(standing.get('EVENT_ID') or '').strip()
					if not player_name or player_name not in per_player:
						continue
					if not event_id:
						continue
					if (event_id, player_name.upper()) not in relevant_player_events:
						continue
					rank_raw = standing.get('EVENT_RANK')
					try:
						rank = int(rank_raw)
					except (TypeError, ValueError):
						continue

					player_standings = standings_by_player.setdefault(
						player_name,
						{
							'finals_wins': 0,
							'top8s': 0,
						}
					)
					if rank == 1:
						player_standings['finals_wins'] += 1
					if rank <= 8:
						player_standings['top8s'] += 1

			leaderboard_rows = []
			for player_name, metrics in per_player.items():
				total_matches = len(metrics['matches'])
				total_events = len(metrics['events'])
				match_wins = metrics['wins']
				match_losses = metrics['losses']
				match_win_pct = (match_wins / (match_wins + match_losses)) if (match_wins + match_losses) > 0 else 0.0

				standing_metrics = standings_by_player.get(player_name, {'finals_wins': 0, 'top8s': 0})
				finals_wins = standing_metrics.get('finals_wins', 0)
				top8s = standing_metrics.get('top8s', 0)
				top8_rate = (top8s / total_events) if total_events > 0 else 0.0

				leaderboard_rows.append({
					'player': player_name,
					'total_matches': total_matches,
					'match_win_pct': match_win_pct,
					'total_events': total_events,
					'finals_wins': finals_wins,
					'top8s': top8s,
					'top8_rate': top8_rate,
				})

			leaderboard_rows.sort(
				key=lambda r: (
					-r['top8s'],
					-r['finals_wins'],
					-r['match_win_pct'],
					-r['total_matches'],
					r['player'].lower(),
				)
			)

			event_history_rows = []
			decks_played_rows = []
			head_to_head_rows = []
			selected_player = player_filter.strip()
			if selected_player:
				selected_player_rows = [
					row for row in player_rows
					if str(row.get('P1') or '').strip().upper() == selected_player.upper()
				]

				event_metrics = {}
				for row in selected_player_rows:
					event_id = str(row.get('EVENT_ID') or '').strip()
					if not event_id:
						continue
					match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
					subarch = _format_vintage_label_value(row.get('p1_subarchetype'))
					metrics = event_metrics.setdefault(
						event_id,
						{
							'wins': 0,
							'losses': 0,
							'deck': '',
							'event_date': row.get('EVENT_DATE'),
							'event_type': _format_vintage_label_value(row.get('EVENT_TYPE')),
						}
					)
					if match_winner == 'P1':
						metrics['wins'] += 1
					elif match_winner == 'P2':
						metrics['losses'] += 1
					if subarch:
						metrics['deck'] = subarch

				event_ids = list(event_metrics.keys())
				if event_ids:
					standings_sql = text(
						'SELECT es."EVENT_ID", es."EVENT_RANK", es."BYES" '
						'FROM "[vapi].EVENT_STANDINGS" es '
						'WHERE UPPER(es."P1") = :selected_player AND es."EVENT_ID" IN :event_ids'
					).bindparams(bindparam('event_ids', expanding=True))
					standings_for_player = [
						dict(r._mapping)
						for r in db.session.execute(
							standings_sql,
							{'selected_player': selected_player.upper(), 'event_ids': event_ids}
						).all()
					]

					for standing in standings_for_player:
						event_id = str(standing.get('EVENT_ID') or '').strip()
						metrics = event_metrics.get(event_id, {})
						byes = standing.get('BYES')
						try:
							byes_num = int(byes) if byes is not None else 0
						except (TypeError, ValueError):
							byes_num = 0

						rank = standing.get('EVENT_RANK')
						try:
							rank_num = int(rank) if rank is not None else None
						except (TypeError, ValueError):
							rank_num = None

						event_date = metrics.get('event_date')
						event_date_text = (
							event_date.strftime('%Y-%m-%d')
							if isinstance(event_date, (datetime.date, datetime.datetime))
							else str(event_date or '')[:10]
						)
						wins = int(metrics.get('wins') or 0)
						losses = int(metrics.get('losses') or 0)
						event_history_rows.append({
							'event_id': event_id,
							'event_date': event_date_text,
							'event_type': metrics.get('event_type') or '',
							'rank': rank_num,
							'record': f'{wins}-{losses}-{byes_num}',
							'deck': metrics.get('deck') or '',
						})

					event_history_rows.sort(
						key=lambda r: (r.get('event_date', ''), r.get('event_id', '')),
						reverse=True,
					)

				deck_metrics = {}
				for row in selected_player_rows:
					match_id = str(row.get('MATCH_ID') or '').strip()
					match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
					subarch = _format_vintage_label_value(row.get('p1_subarchetype'))
					if not subarch or subarch.upper() in {'NA', 'NO SHOW'}:
						continue

					metrics = deck_metrics.setdefault(
						subarch,
						{
							'matches': set(),
							'wins': 0,
							'losses': 0,
						}
					)
					if match_id:
						metrics['matches'].add(match_id)
					if match_winner == 'P1':
						metrics['wins'] += 1
					elif match_winner == 'P2':
						metrics['losses'] += 1

				for subarch, metrics in deck_metrics.items():
					total_matches = len(metrics['matches'])
					wins = int(metrics['wins'] or 0)
					losses = int(metrics['losses'] or 0)
					match_win_pct = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
					decks_played_rows.append({
						'subarchetype': subarch,
						'total_matches': total_matches,
						'match_win_pct': match_win_pct,
					})

				decks_played_rows.sort(
					key=lambda r: (-r['total_matches'], -r['match_win_pct'], r['subarchetype'].lower())
				)

				h2h_metrics = {}
				for row_index, row in enumerate(selected_player_rows):
					opponent = str(row.get('P2') or '').strip()
					if not opponent:
						continue
					match_id = str(row.get('MATCH_ID') or '').strip()
					match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
					metric_key = match_id or f'row:{row_index}'

					metrics = h2h_metrics.setdefault(
						opponent,
						{
							'matches': set(),
							'wins': 0,
							'losses': 0,
						}
					)
					if metric_key in metrics['matches']:
						continue
					metrics['matches'].add(metric_key)

					if match_winner == 'P1':
						metrics['wins'] += 1
					elif match_winner == 'P2':
						metrics['losses'] += 1

				for opponent, metrics in h2h_metrics.items():
					total_matches = len(metrics['matches'])
					wins = int(metrics['wins'] or 0)
					losses = int(metrics['losses'] or 0)
					match_win_pct = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
					head_to_head_rows.append({
						'opponent': opponent,
						'total_matches': total_matches,
						'record': f'{wins}-{losses}',
						'match_win_pct': match_win_pct,
					})

				head_to_head_rows.sort(
					key=lambda r: (-r['total_matches'], -r['match_win_pct'], r['opponent'].lower())
				)

			return _cache_and_return_vintage_dashboard_data(
				cache_key,
				{
					'unique_players': len(per_player),
					'selected_player': selected_player,
					'leaderboard_rows': leaderboard_rows,
					'event_history_rows': event_history_rows,
					'decks_played_rows': decks_played_rows,
					'head_to_head_rows': head_to_head_rows,
				}
			)

		# event-explorer
		event_explorer_sql = text(
			'SELECT '
			'  m."EVENT_ID", '
			'  m."MATCH_ID", '
			'  m."P1", '
			'  m."MATCH_WINNER", '
			'  e."EVENT_DATE", '
			'  vet."EVENT_TYPE", '
			'  vd1."ARCHETYPE" AS p1_archetype, '
			'  vd1."SUBARCHETYPE" AS p1_subarchetype, '
			'  vd2."ARCHETYPE" AS p2_archetype, '
			'  vd2."SUBARCHETYPE" AS p2_subarchetype '
			'FROM "[vapi].MATCHES" m '
			'LEFT JOIN "[vapi].EVENTS" e ON m."EVENT_ID" = e."EVENT_ID" '
			'LEFT JOIN "[vapi].VALID_EVENT_TYPES" vet ON e."EVENT_TYPE_ID" = vet."EVENT_TYPE_ID" '
			'LEFT JOIN "[vapi].VALID_DECKS" vd1 ON m."P1_DECK_ID" = vd1."DECK_ID" '
			'LEFT JOIN "[vapi].VALID_DECKS" vd2 ON m."P2_DECK_ID" = vd2."DECK_ID" '
			f'{where_clause}'
		)
		rows = [dict(r._mapping) for r in db.session.execute(event_explorer_sql, params).all()]

		unique_players = len({
			(str(row.get('P1') or '').strip())
			for row in rows
			if str(row.get('P1') or '').strip()
		})

		event_summary = {}
		player_agg = {}
		for row in rows:
			def _safe_text(value):
				return str(value).strip() if value is not None else ''

			event_id = _safe_text(row.get('EVENT_ID'))
			player = _safe_text(row.get('P1'))
			match_id = _safe_text(row.get('MATCH_ID'))
			match_winner = (row.get('MATCH_WINNER') or '').strip().upper()
			event_date = row.get('EVENT_DATE')
			event_type_raw = row.get('EVENT_TYPE')
			p1_arch = _safe_text(row.get('p1_archetype'))
			p1_subarch = _safe_text(row.get('p1_subarchetype'))

			if not event_id:
				continue

			if event_id not in event_summary:
				event_summary[event_id] = {
					'event_id': event_id,
					'event_type': _format_vintage_label_value(event_type_raw),
					'event_date': event_date.strftime('%Y-%m-%d') if isinstance(event_date, (datetime.date, datetime.datetime)) else str(event_date or '')[:10],
					'players': set(),
				}
			if player:
				event_summary[event_id]['players'].add(player)

			if player and match_id:
				if selected_event_id and event_id != selected_event_id:
					continue
				player_key = (event_id, player)
				if player_key not in player_agg:
					player_agg[player_key] = {
						'wins': 0,
						'losses': 0,
						'arch': p1_arch,
						'subarch': p1_subarch,
					}
				if match_winner == 'P1':
					player_agg[player_key]['wins'] += 1
				elif match_winner == 'P2':
					player_agg[player_key]['losses'] += 1
				# Keep most recent non-empty archetype/subarchetype if needed.
				if p1_arch:
					player_agg[player_key]['arch'] = p1_arch
				if p1_subarch:
					player_agg[player_key]['subarch'] = p1_subarch

		event_rows = [
			{
				'event_id': event_id,
				'event_type': summary['event_type'],
				'date': summary['event_date'],
				'players': len(summary['players']),
			}
			for event_id, summary in event_summary.items()
		]
		event_rows.sort(key=lambda r: (r['date'], r['event_id']), reverse=True)

		standings_rows = []
		if selected_event_id:
			standings_sql = text(
				'SELECT es."EVENT_ID", es."EVENT_RANK", es."P1", es."BYES" '
				'FROM "[vapi].EVENT_STANDINGS" es '
				'WHERE es."EVENT_ID" = :event_id'
			)

			standings_raw = [dict(r._mapping) for r in db.session.execute(standings_sql, {'event_id': selected_event_id}).all()]
			for standing in standings_raw:
				def _safe_text(value):
					return str(value).strip() if value is not None else ''

				def _safe_int(value, default=None):
					if value is None:
						return default
					try:
						return int(value)
					except (TypeError, ValueError):
						try:
							return int(float(str(value).strip()))
						except (TypeError, ValueError):
							return default

				event_id = _safe_text(standing.get('EVENT_ID'))
				player = _safe_text(standing.get('P1'))
				player_key = (event_id, player)
				agg = player_agg.get(player_key)
				if not agg:
					continue

				arch_formatted = _format_vintage_label_value(agg.get('arch'))
				subarch_formatted = _format_vintage_label_value(agg.get('subarch'))
				deck_value = subarch_formatted or arch_formatted

				standings_rows.append({
					'event_id': event_id,
					'rank': _safe_int(standing.get('EVENT_RANK')),
					'player': player,
					'wins': agg.get('wins', 0),
					'losses': agg.get('losses', 0),
					'byes': _safe_int(standing.get('BYES'), 0),
					'deck': deck_value,
					'event_date': event_summary.get(event_id, {}).get('event_date', ''),
				})

		standings_rows.sort(
			key=lambda r: (
				r.get('event_date', ''),
				r.get('event_id', ''),
				(r.get('rank') if r.get('rank') is not None else 10**9),
				(r.get('player') or '').lower(),
			),
			reverse=False,
		)

		event_scatter_rows = []
		event_bar_rows = []
		event_matchup_heatmap = {'subarchetypes': [], 'rows': []}
		heatmap_source_rows = rows
		if selected_event_id:
			selected_rows = [
				r for r in rows
				if str(r.get('EVENT_ID') or '').strip() == selected_event_id
			]
			heatmap_source_rows = selected_rows
			event_scatter_rows = _compute_vintage_metagame_table(
				rows=selected_rows,
				key_field='p1_subarchetype',
				opp_key_field='p2_subarchetype',
				excluded_values={'NA', 'NO SHOW'},
			)
			event_bar_rows = _compute_vintage_metagame_table(
				rows=selected_rows,
				key_field='p1_archetype',
				opp_key_field='p2_archetype',
				excluded_values={'NA'},
			)

		# Build subarchetype matchup matrix (row subarchetype vs column subarchetype).
		subarchetypes_present = set()
		matchup_metrics = {}
		for row in heatmap_source_rows:
			left_subarch = _format_vintage_label_value(row.get('p1_subarchetype'))
			top_subarch = _format_vintage_label_value(row.get('p2_subarchetype'))
			match_winner = str(row.get('MATCH_WINNER') or '').strip().upper()
			if (
				not left_subarch
				or not top_subarch
				or left_subarch.upper() in {'NA', 'NO SHOW'}
				or top_subarch.upper() in {'NA', 'NO SHOW'}
			):
				continue

			subarchetypes_present.add(left_subarch)
			subarchetypes_present.add(top_subarch)
			key = (left_subarch, top_subarch)
			metrics = matchup_metrics.setdefault(
				key,
				{
					'wins': 0,
					'losses': 0,
				}
			)
			if match_winner == 'P1':
				metrics['wins'] += 1
			elif match_winner == 'P2':
				metrics['losses'] += 1

		sorted_subarchetypes = sorted(subarchetypes_present, key=lambda value: value.lower())
		heatmap_rows = []
		for left_subarch in sorted_subarchetypes:
			cells = []
			for top_subarch in sorted_subarchetypes:
				metrics = matchup_metrics.get((left_subarch, top_subarch), {'wins': 0, 'losses': 0})
				wins = int(metrics.get('wins') or 0)
				losses = int(metrics.get('losses') or 0)
				total_matches = wins + losses
				match_win_pct = (wins / total_matches) if total_matches > 0 else None
				cells.append({
					'opponent': top_subarch,
					'total_matches': total_matches,
					'match_win_pct': match_win_pct,
				})
			heatmap_rows.append({
				'subarchetype': left_subarch,
				'cells': cells,
			})

		event_matchup_heatmap = {
			'subarchetypes': sorted_subarchetypes,
			'rows': heatmap_rows,
		}

		winner = None
		runner_up = None
		if selected_event_id and standings_rows:
			event_standings = [r for r in standings_rows if r.get('event_id') == selected_event_id]
			if event_standings:
				event_standings.sort(
					key=lambda r: (
						(r.get('rank') if r.get('rank') is not None else 10**9),
						-(r.get('wins') or 0),
						(r.get('losses') or 0),
						(r.get('player') or '').lower(),
					)
				)
				top_row = event_standings[0]
				winner = {
					'player': top_row.get('player') or '--',
					'deck': top_row.get('deck') or 'Selected event',
				}
				if len(event_standings) > 1:
					second_row = event_standings[1]
					runner_up = {
						'player': second_row.get('player') or '--',
						'deck': second_row.get('deck') or 'Selected event',
					}

		if dashboard_type == 'matchup-heatmap':
			return _cache_and_return_vintage_dashboard_data(
				cache_key,
				{
					'unique_players': unique_players,
					'selected_event_id': selected_event_id,
					'event_matchup_heatmap': event_matchup_heatmap,
				}
			)

		return _cache_and_return_vintage_dashboard_data(
			cache_key,
			{
				'unique_players': unique_players,
				'selected_event_id': selected_event_id,
				'winner': winner,
				'runner_up': runner_up,
				'event_rows': event_rows,
				'standings_rows': standings_rows,
				'event_scatter_rows': event_scatter_rows,
				'event_bar_rows': event_bar_rows,
				'event_matchup_heatmap': event_matchup_heatmap,
			}
		)

	except Exception as error:
		debug_log(f'Error generating vintage dashboard: {error}')
		return jsonify({'success': False, 'error': 'Failed to generate vintage dashboard'}), 500