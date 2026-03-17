from flask import render_template, request, Blueprint, flash, redirect, send_file, Response, jsonify, redirect, url_for, current_app, session, after_this_request
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, create_engine, desc, select, and_, asc, case
from sqlalchemy.sql.expression import not_
from flask_login import login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import datetime
from modules.models import (
	Player,
	Match,
	Game,
	Play,
	Pick,
	Draft,
	GameActions,
	Removed,
	CardsPlayed,
	TaskHistory,
	InputOption,
	MultifacedCard,
	AllDeck,
)
from modules.extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os
import io
import time
from modules import modo
import pickle
import math 
import pandas as pd
import zipfile
import requests
from celery import shared_task
from celery.contrib.abortable import AbortableTask
import boto3
from botocore.exceptions import ClientError
import pytz
import json
import logging
import threading
#logging.getLogger("smtplib").setLevel(logging.ERROR)
#logging.getLogger("celery").setLevel(logging.ERROR)

# Debug logging function
def debug_log(message):
	"""Log debug messages to both console and file"""
	timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	log_message = f"[{timestamp}] {message}"
	
	# Print to console
	print(log_message)
	
	# Write to log file
	# try:
	# 	log_dir = os.path.join('local-dev', 'data', 'logs')
	# 	os.makedirs(log_dir, exist_ok=True)
	# 	log_file = os.path.join(log_dir, 'debug_log.txt')
		
	# 	with open(log_file, 'a', encoding='utf-8') as f:
	# 		f.write(log_message + '\n')
	# 	except Exception as e:
	# 		debug_log(f"Warning: Could not write to log file: {e}")

page_size = 20

# Initialize S3 client if configured
try:
    S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
    S3_PREFIX = os.environ.get('S3_PREFIX', '').strip()
    if S3_PREFIX and not S3_PREFIX.endswith('/'):
        S3_PREFIX = S3_PREFIX + '/'
    if S3_BUCKET_NAME:
        s3_client = boto3.client('s3', region_name=os.environ.get('AWS_REGION'))
        S3_ENABLED = True
        debug_log(f"S3 enabled for bucket: {S3_BUCKET_NAME}")
    else:
        s3_client = None
        S3_ENABLED = False
        debug_log("S3 bucket not configured - using local storage")
except Exception as e:
    s3_client = None
    S3_ENABLED = False
    debug_log(f"Failed to initialize S3 client: {e}")

s = URLSafeTimedSerializer(os.environ.get("URL_SAFETIMEDSERIALIZER", "dev-secret-key"))
views = Blueprint('views', __name__)

DEFAULT_PROFILE_IMAGE = 'Waterspout-Warden.png'

def compute_sidebar_status_for_user(uid):
    """Compute sidebar enable/disable status for a given user id."""
    match_count = Match.query.filter_by(uid=uid).count()
    draft_count = Draft.query.filter_by(uid=uid).count()
    removed_count = Removed.query.filter_by(uid=uid).count()
    game_actions_count = GameActions.query.filter_by(uid=uid).count()

    # Check if there are GameActions with valid match_ids (exist in Match table)
    valid_game_actions_count = 0
    if game_actions_count > 0:
        game_action_match_ids = db.session.query(GameActions.match_id).filter_by(uid=uid).distinct().all()
        game_action_match_ids = [row[0] for row in game_action_match_ids]
        if game_action_match_ids:
            valid_match_ids = db.session.query(Match.match_id).filter(
                Match.uid == uid,
                Match.match_id.in_(game_action_match_ids)
            ).all()
            valid_match_ids = [row[0] for row in valid_match_ids]
            if valid_match_ids:
                valid_game_actions_count = GameActions.query.filter(
                    GameActions.uid == uid,
                    GameActions.match_id.in_(valid_match_ids)
                ).count()

    # Check if archive directory has files for reprocessing
    archive_files_count = 0
    archive_dir = os.path.join('local-dev', 'data', 'uploads', str(uid))
    if os.path.exists(archive_dir):
        all_files = os.listdir(archive_dir)
        for filename in all_files:
            if not filename.endswith('.meta'):
                log_type = get_logtype_from_filename(filename)
                if log_type in ['GameLog', 'DraftLog']:
                    archive_files_count += 1

    return {
        'matches_enabled': match_count > 0,
        'best_guess_enabled': match_count > 0,
        'drafts_enabled': draft_count > 0,
        'ignored_matches_enabled': removed_count > 0,
        'missing_winners_enabled': valid_game_actions_count > 0,
        'draft_ids_enabled': match_count > 0 and draft_count > 0,
        'reprocess_enabled': archive_files_count > 0,
        'export_enabled': match_count > 0 or draft_count > 0,
        'dashboards_enabled': match_count > 0 or draft_count > 0
    }

@views.app_context_processor
def inject_initial_sidebar_status():
    try:
        if current_user and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            status = compute_sidebar_status_for_user(current_user.uid)
            return {'initial_sidebar_status': status}
    except Exception:
        pass
    return {'initial_sidebar_status': None}

def update_draft_wins(uid, username, draft_id):
	"""Update draft match statistics - shared function used by multiple processes"""
	match_wins = 0
	match_losses = 0
	proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	print(f"🔍 UPDATE DRAFT WINS DEBUG: uid = {uid}, username = {username}, draft_id = {draft_id}")
	associated_matches = Match.query.filter_by(
		uid=uid, 
		draft_id=draft_id, 
		p1=username
	)
	
	for match in associated_matches:
		if match.p1_wins > match.p2_wins:
			match_wins += 1
		elif match.p2_wins > match.p1_wins:
			match_losses += 1
	
	draft = Draft.query.filter_by(
		uid=uid, 
		draft_id=draft_id
	).first()
	
	if draft:
		draft.match_wins = match_wins
		draft.match_losses = match_losses
		draft.proc_dt = proc_dt

	try:
		db.session.commit()
	except Exception as e:
		db.session.rollback()
		debug_log(f"Error committing draft ID update: {str(e)}")

REFERENCE_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
reference_data_cache_lock = threading.Lock()
reference_data_cache = {
	'input_options': {'data': None, 'loaded_at': 0.0},
	'multifaced_cards': {'data': None, 'loaded_at': 0.0},
	'all_decks': {'data': None, 'loaded_at': 0.0},
}

def _is_cache_entry_valid(entry):
	if entry['data'] is None:
		return False
	return (time.time() - entry['loaded_at']) < REFERENCE_CACHE_TTL_SECONDS

def _get_cached_reference_data(cache_key, loader, force_refresh=False):
	with reference_data_cache_lock:
		entry = reference_data_cache[cache_key]
		if (not force_refresh) and _is_cache_entry_valid(entry):
			return entry['data']

	data = loader()

	with reference_data_cache_lock:
		reference_data_cache[cache_key]['data'] = data
		reference_data_cache[cache_key]['loaded_at'] = time.time()

	return data

def _load_input_options_from_db():
	"""Load input options from database table and emit legacy key names."""
	legacy_key_by_var = {
		"Match_Type_Constructed": "Constructed Match Types",
		"Match_Type_Booster_Draft": "Booster Draft Match Types",
		"Match_Type_Sealed": "Sealed Match Types",
		"P1_P2_Arch": "Archetypes",
		"Format_Constructed": "Constructed Formats",
		"Format_Limited": "Limited Formats",
		"Limited_Format_Cube": "Cube Formats",
		"Limited_Format_Booster_Draft": "Booster Draft Formats",
		"Limited_Format_Sealed": "Sealed Formats",
	}

	try:
		rows = InputOption.query.order_by(InputOption.table_nm, InputOption.var_nm).all()
		input_options = {key: [] for key in legacy_key_by_var.values()}

		for row in rows:
			key = legacy_key_by_var.get(row.var_nm)
			if key is None:
				continue

			value = row.options_lst if isinstance(row.options_lst, list) else []
			input_options[key].extend(str(item) for item in value if item is not None)

		# Remove duplicates while preserving order.
		for key, values in input_options.items():
			input_options[key] = list(dict.fromkeys(values))

		debug_log(f"Loaded input options with {len(input_options)} categories from database table")
		return input_options

	except Exception as e:
		debug_log(f"Error reading input options from database: {e}")
		return {}

def get_input_options(force_refresh=False):
	"""Get cached input options with a 7-day TTL."""
	return _get_cached_reference_data('input_options', _load_input_options_from_db, force_refresh=force_refresh)

def get_column_widths(table_name):
	"""Get column widths for different table types - Updated v2.0"""
	widths = {
		# Matches: 10 columns = 100% (compact display)
		'matches': ["11%", "9%", "10%", "9%", "10%", "9%", "9%", "11%", "11%", "11%"],
		# Games: 10 columns = 100% (combined mulligans)
		'games': ["12%", "12%", "8%", "10%", "10%", "9%", "9%", "10%", "10%", "10%"],
		# Plays: 12 columns = 100% (active/non-active hidden)
		'plays': ["6%", "5%", "5%", "10%", "9%", "11%", "12%", "8%", "8%", "9%", "10%", "7%"],
		# Drafts: 11 columns - wins/losses combined into Match Score
		'drafts': ["9%", "9%", "9%", "9%", "9%", "9%", "9%", "9%", "8%", "9%", "11%"],
		# Picks: 16 columns - Pick # includes overall
		'picks': ["12%", "7%", "5%", "5%", "5%", "6%", "6%", "6%", "6%", "6%", "6%", "6%", "6%", "6%", "6%", "6%"],
		# Ignored: 3 columns = 100%
		'ignored': ["40%", "30%", "30%"]
	}
	return widths.get(table_name.lower(), [])

def _load_multifaced_cards_from_db():
	"""Load multifaced cards from database table."""
	multifaced_cards = {key: {} for key in ("SPLIT", "TRANSFORM", "DFC", "MDFC", "ADVENTURE")}

	try:
		rows = MultifacedCard.query.order_by(
			MultifacedCard.mult_type,
			MultifacedCard.front_nm,
		).all()
		for row in rows:
			card_map = multifaced_cards.setdefault(row.mult_type, {})
			card_map[row.front_nm] = row.back_nm

		debug_log(f"Loaded {len(rows)} multifaced cards from database table")
		return multifaced_cards

	except Exception as e:
		debug_log(f"Error reading multifaced cards from database: {e}")
		return {}

def get_multifaced_cards(force_refresh=False):
	"""Get cached multifaced cards with a 7-day TTL."""
	return _get_cached_reference_data('multifaced_cards', _load_multifaced_cards_from_db, force_refresh=force_refresh)

def _load_all_decks_from_db():
	"""Load all decks from database table with legacy in-memory structure."""
	try:
		rows = AllDeck.query.order_by(
			AllDeck.yyyy_mm,
			AllDeck.deck_nm,
			AllDeck.format_nm,
		).all()

		all_decks = {}
		for row in rows:
			cards = row.deck_lst if isinstance(row.deck_lst, list) else []
			entry = [row.deck_nm, row.format_nm, set(str(card) for card in cards)]
			all_decks.setdefault(row.yyyy_mm, []).append(entry)

		debug_log(f"Loaded {len(all_decks)} deck months from database table")
		return all_decks

	except Exception as e:
		debug_log(f"Error reading all decks from database: {e}")
		return {}

def get_all_decks(force_refresh=False):
	"""Get cached all_decks with a 7-day TTL."""
	return _get_cached_reference_data('all_decks', _load_all_decks_from_db, force_refresh=force_refresh)
def build_cards_played_db(uid):
	#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Building cards played database for user {uid}")
	
	try:
		# Ensure global variables are loaded
		ensure_data_loaded()
		#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Global variables loaded")
		
		query = db.session.query(Match.match_id).filter_by(uid=uid).distinct()
		match_ids = [value[0] for value in query.all()]
		#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Found {len(match_ids)} unique match IDs")
		
		cards_added = 0
		proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		for i in match_ids:
			#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Processing match {i}")
			
			if CardsPlayed.query.filter_by(uid=uid, match_id=i).first():
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} already exists, skipping")
				continue
				
			try:
				players = [value[0] for value in db.session.query(Play.casting_player).filter_by(uid=uid, match_id=i).distinct().all()]
				
				if len(players) < 2:
					#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Match {i} has insufficient players ({len(players)}), skipping")
					continue

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[0], action='Casts').distinct()
				plays1 = [value[0] for value in query.all()]
				plays1 = modo.clean_card_set(set(plays1),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[1], action='Casts').distinct()
				plays2 = [value[0] for value in query.all()]
				plays2 = modo.clean_card_set(set(plays2),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[0], action='Land Drop').distinct()
				lands1 = [value[0] for value in query.all()]
				lands1 = modo.clean_card_set(set(lands1),multifaced)

				query = db.session.query(Play.primary_card).filter_by(uid=uid, match_id=i, casting_player=players[1], action='Land Drop').distinct()
				lands2 = [value[0] for value in query.all()]
				lands2 = modo.clean_card_set(set(lands2),multifaced)

				cards_played = CardsPlayed(uid=uid,
											match_id=i,
											casting_player1=players[0],
											casting_player2=players[1],
											plays1=sorted(list(plays1),reverse=False),
											plays2=sorted(list(plays2),reverse=False),
											lands1=sorted(list(lands1),reverse=False),
											lands2=sorted(list(lands2),reverse=False),
											proc_dt=proc_dt)
				db.session.add(cards_played)
				cards_added += 1
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Added cards played for match {i}")
				
			except Exception as e:
				#debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to process match {i}: {e}")
				continue
		
		# Single commit at the end for better performance
		if cards_added > 0:
			try:
				db.session.commit()
				#debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: Successfully committed {cards_added} cards played records")
			except Exception as e:
				#debug_log(f"🔍 BUILD CARDS PLAYED ERROR: Failed to commit: {e}")
				db.session.rollback()
		else:
			debug_log(f"🔍 BUILD CARDS PLAYED DEBUG: No new cards played records to add")
			
	except Exception as e:
		#debug_log(f"🔍 BUILD CARDS PLAYED CRITICAL ERROR: {e}")
		try:
			db.session.rollback()
		except:
			pass
def update_draft_win_loss(uid, username, draft_id):
	if draft_id != 'NA':
		draft_record = Draft.query.filter_by(uid=uid, draft_id=draft_id, hero=username).first()
		wins = Match.query.filter_by(uid=uid, draft_id=draft_id, p1=username, match_winner='P1').count()
		losses = Match.query.filter_by(uid=uid, draft_id=draft_id, p1=username, match_winner='P2').count()
		draft_record.match_wins = wins
		draft_record.match_losses = losses
		try:
			db.session.commit()
		except:
			db.session.rollback()
def get_logtype_from_filename(filename):
	# GameLog example: contains Match_GameLog_ and ends with .dat
	if ('Match_GameLog_' in filename) and filename.lower().endswith('.dat') and len(filename) >= 30:
		return 'GameLog'

	# DraftLog heuristic must mirror zip_mtgo_logs.py
	if (filename.count('.') != 3) or (filename.count('-') != 4) or (not filename.lower().endswith('.txt')):
		return 'NA'
	split_dash = filename.split('-')
	try:
		# Year part (from date YYYY.MM.DD) must be 4 digits;
		# next segment is numeric ID (allow 4-6 digits)
		year_part = split_dash[1].split('.')[0]
		id_part = split_dash[2]
		if len(year_part) != 4 or not (4 <= len(id_part) <= 6 and id_part.isdigit()):
			return 'NA'
	except Exception:
		return 'NA'
	return 'DraftLog'

@shared_task(bind=True, base=AbortableTask)
def process_logs(self, data):
	def extract_zip_file(zip_ref, path):
		skipped = 0
		uploaded = 0
		new_files = []
		replaced_files = []
		skipped_files = []
		
		# Create local storage directory if it doesn't exist
		if not S3_ENABLED:  # Local mode
			local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(data['user_id']))
			os.makedirs(local_storage_dir, exist_ok=True)
			debug_log(f"🔍 EXTRACT DEBUG: Using local storage: {local_storage_dir}")
		
		debug_log(f"🔍 EXTRACT DEBUG: Processing {len(zip_ref.infolist())} files from zip")
		for member in zip_ref.infolist():
			debug_log(f"🔍 EXTRACT DEBUG: Processing zip member: {member.filename}")
			
			logtype = get_logtype_from_filename(member.filename)
			debug_log(f"🔍 EXTRACT DEBUG: File {member.filename} has logtype: {logtype}")
			
			if get_logtype_from_filename(member.filename) == 'NA':
				debug_log(f"🔍 EXTRACT DEBUG: Skipping {member.filename} - logtype is NA")
				skipped += 1
				continue
			
			if not S3_ENABLED:  # Local file storage
				# Local file storage logic
				local_file_path = os.path.join(local_storage_dir, member.filename)
				new_mtime = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
				debug_log(f"🔍 EXTRACT DEBUG: Local file path: {local_file_path}")
				debug_log(f"🔍 EXTRACT DEBUG: New file mtime: {new_mtime}")
				
				# Check if file exists locally
				if os.path.exists(local_file_path):
					debug_log(f"🔍 EXTRACT DEBUG: File exists locally: {local_file_path}")
					# Read existing metadata from a companion .meta file
					meta_file = local_file_path + '.meta'
					if os.path.exists(meta_file):
						with open(meta_file, 'r') as f:
							existing_mtime = f.read().strip()
						debug_log(f"🔍 EXTRACT DEBUG: Existing mtime: {existing_mtime}, New mtime: {new_mtime}")
						if new_mtime >= existing_mtime:
							debug_log(f"🔍 EXTRACT DEBUG: Skipping {member.filename} - new mtime >= existing mtime")
							skipped_files.append(member.filename.split('/')[-1])
							skipped += 1
							continue
						else:
							debug_log(f"🔍 EXTRACT DEBUG: Replacing {member.filename} - new mtime < existing mtime")
							# Replace with newer file
							zip_ref.extract(member, local_storage_dir)
							# Move file to final location and save metadata
							extracted_path = os.path.join(local_storage_dir, member.filename)
							if extracted_path != local_file_path:
								os.rename(extracted_path, local_file_path)
							with open(meta_file, 'w') as f:
								f.write(new_mtime)
							replaced_files.append(member.filename.split('/')[-1])
							uploaded += 1
					else:
						debug_log(f"🔍 EXTRACT DEBUG: File exists but no metadata - replacing {member.filename}")
						# File exists but no metadata, replace it
						zip_ref.extract(member, local_storage_dir)
						extracted_path = os.path.join(local_storage_dir, member.filename)
						if extracted_path != local_file_path:
							os.rename(extracted_path, local_file_path)
						with open(local_file_path + '.meta', 'w') as f:
							f.write(new_mtime)
						replaced_files.append(member.filename.split('/')[-1])
						uploaded += 1
				else:
					debug_log(f"🔍 EXTRACT DEBUG: New file - extracting {member.filename}")
					# New file
					zip_ref.extract(member, local_storage_dir)
					extracted_path = os.path.join(local_storage_dir, member.filename)
					if extracted_path != local_file_path:
						os.rename(extracted_path, local_file_path)
					with open(local_file_path + '.meta', 'w') as f:
						f.write(new_mtime)
					new_files.append(member.filename.split('/')[-1])
					uploaded += 1
			else:  # S3 storage
				s3_key = f"{path}{member.filename}"
				new_mtime = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
				# Check if object exists
				try:
					resp = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=S3_PREFIX + s3_key)
					existing_mtime = resp.get('Metadata', {}).get('original_mod_time')
					if existing_mtime and new_mtime >= existing_mtime:
						skipped_files.append(member.filename.split('/')[-1])
						skipped += 1
					else:
						zip_ref.extract(member, os.getcwd())
						with open(member.filename, 'rb') as file_to_upload:
							s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=S3_PREFIX + s3_key, Body=file_to_upload, Metadata={'original_mod_time': new_mtime})
						replaced_files.append(member.filename.split('/')[-1])
						os.remove(member.filename)
						uploaded += 1
				except ClientError as e:
					if e.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound'):
						# New object
						file_mod_time = time.strftime('%Y%m%d%H%M', member.date_time + (0, 0, -1))
						zip_ref.extract(member, os.getcwd())
						with open(member.filename, 'rb') as file_to_upload:
							s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=S3_PREFIX + s3_key, Body=file_to_upload, Metadata={'original_mod_time': file_mod_time})
						new_files.append(member.filename.split('/')[-1])
						os.remove(member.filename)
						uploaded += 1
					else:
						raise
		debug_log(f"🔍 EXTRACT DEBUG: Extraction complete - skipped: {skipped}, uploaded: {uploaded}")
		debug_log(f"🔍 EXTRACT DEBUG: new_files: {new_files}")
		debug_log(f"🔍 EXTRACT DEBUG: replaced_files: {replaced_files}")
		debug_log(f"🔍 EXTRACT DEBUG: skipped_files: {skipped_files}")
		return {'skipped':skipped,'uploaded':uploaded, 'new_files':new_files, 'replaced_files':replaced_files, 'skipped_files':skipped_files}
	
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'matches_replaced':0,
		'games_replaced':0,
		'plays_replaced':0,
		'drafts_replaced':0,
		'picks_replaced':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0,
	}
	game_errors = {}
	draft_errors = {}
	uid = data['user_id']
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None
	file_stream = io.BytesIO(data['file_stream'])

	with zipfile.ZipFile(file_stream, 'r') as zip_ref:
		upload_dict = extract_zip_file(zip_ref, f"{uid}/")
	
	try:
		# Get list of files to process based on storage type
		files_to_process = []
		
		if not S3_ENABLED:  # Local file storage
			local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(uid))
			debug_log(f"🔍 DEBUG: Looking for files in: {local_storage_dir}")
			debug_log(f"🔍 DEBUG: Directory exists: {os.path.exists(local_storage_dir)}")
			if os.path.exists(local_storage_dir):
				all_files = os.listdir(local_storage_dir)
				debug_log(f"🔍 DEBUG: Found {len(all_files)} total files: {all_files}")
				debug_log(f"🔍 DEBUG: Skipped files from upload_dict: {upload_dict['skipped_files']}")
				for filename in all_files:
					debug_log(f"🔍 DEBUG: Processing file: {filename}")
					if filename.endswith('.meta'):  # Skip metadata files
						debug_log(f"🔍 DEBUG: Skipping {filename} (metadata file)")
						continue
					if filename in upload_dict['skipped_files']:
						debug_log(f"🔍 DEBUG: Skipping {filename} (in skipped_files)")
						continue
					
					local_file_path = os.path.join(local_storage_dir, filename)
					meta_file_path = local_file_path + '.meta'
					
					# Read metadata
					if os.path.exists(meta_file_path):
						with open(meta_file_path, 'r') as f:
							mtime = f.read().strip()
					else:
						mtime = '202301010000'  # Default fallback
					
					log_type = get_logtype_from_filename(filename)
					debug_log(f"🔍 DEBUG: File {filename} detected as log_type: '{log_type}'")
					if log_type in ['GameLog', 'DraftLog']:
						debug_log(f"🔍 DEBUG: Adding {filename} to files_to_process")
						files_to_process.append({
							'filename': filename,
							'path': local_file_path,
							'mtime': mtime,
							'storage_type': 'local',
							'log_type': log_type
						})
					else:
						debug_log(f"🔍 DEBUG: Skipping {filename} - log_type '{log_type}' not in ['GameLog', 'DraftLog']")
			else:
				debug_log(f"🔍 DEBUG: Local storage directory does not exist: {local_storage_dir}")
		else:  # S3 storage
			prefix = f"{S3_PREFIX}{uid}/"
			paginator = s3_client.get_paginator('list_objects_v2')
			for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix):
				for obj in page.get('Contents', []):
					key = obj['Key']
					filename = key.split('/')[-1]
					if filename in upload_dict['skipped_files']:
						continue
					if get_logtype_from_filename(filename) in ['GameLog', 'DraftLog']:
						try:
							head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=key)
							mtime = head.get('Metadata', {}).get('original_mod_time', '202301010000')
							files_to_process.append({
								'filename': filename,
								's3_key': key,
								'mtime': mtime,
								'storage_type': 's3',
								'log_type': get_logtype_from_filename(filename)
							})
						except ClientError:
							continue
		
		# Now process all files with unified logic
		debug_log(f"🔍 Processing {len(files_to_process)} files")
		
		# Database and email operations - get Flask app from Celery BEFORE processing files
		from app import create_app
		app = create_app()
		
		proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		with app.app_context():
			for file_info in files_to_process:
				filename = file_info['filename']
				mtime = file_info['mtime']
				log_type = file_info['log_type']
				
				# Read file content based on storage type
				if file_info['storage_type'] == 'local':
					with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
						initial = f.read().replace('\x00','')
				elif file_info['storage_type'] == 's3':
					obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_info['s3_key'])
					body = obj['Body'].read()
					initial = body.decode('utf-8', errors='ignore').replace('\r','').replace('\x00','')

				# Process based on log type
				if log_type == 'GameLog':
					fname = filename.split('_')[-1].split('.dat')[0]
					
					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['gamelogs_skipped_removed'] += 1
						continue

					try:
						parsed_data = modo.get_all_data(initial,mtime,fname)
						parsed_data_inverted = modo.invert_join([[parsed_data[0]], parsed_data[1], parsed_data[2], parsed_data[3], parsed_data[4]])
						counts['total_gamelogs'] += 1
					except Exception as error:
						counts['gamelogs_skipped_error'] += 1
						if str(error) in game_errors:
							game_errors[str(error)] += 1
						else:
							game_errors[str(error)] = 0
						continue

					if len(parsed_data_inverted[2]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, date=mtime, reason='Empty', proc_dt=proc_dt)
						db.session.add(newIgnore)
						counts['gamelogs_skipped_empty'] += 1
						continue
				
				elif log_type == 'DraftLog':
					debug_log(f"🔍 DRAFTLOG DEBUG: Processing DraftLog file: {filename}")
					try:
						parsed_data = modo.parse_draft_log(filename, initial)
						debug_log(f"🔍 DRAFTLOG DEBUG: Successfully parsed {filename}")
						debug_log(f"🔍 DRAFTLOG DEBUG: parsed_data[0] (drafts) length: {len(parsed_data[0])}")
						debug_log(f"🔍 DRAFTLOG DEBUG: parsed_data[1] (picks) length: {len(parsed_data[1])}")
						counts['total_draftlogs'] += 1
					except Exception as error:
						debug_log(f"🔍 DRAFTLOG DEBUG: Failed to parse {filename}: {error}")
						counts['draftlogs_skipped_error'] += 1
						if str(error) in draft_errors:
							draft_errors[str(error)] += 1
						else:
							draft_errors[str(error)] = 0
						continue

				# Continue with processing parsed data for both GameLog and DraftLog
				if log_type == 'GameLog':
					# GameLog database operations
					for match in parsed_data_inverted[0]:
						if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
							existing = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
							existing.p2 = match[5]
							existing.p1_roll = match[8]
							existing.p2_roll = match[9]
							existing.roll_winner = match[10]
							existing.date = match[17]
							existing.proc_dt = proc_dt
							Play.query.filter_by(uid=uid, match_id=match[0]).delete()
							try:
								db.session.commit()
							except:
								db.session.rollback()
							counts['matches_replaced'] += 1
						else:
							new_match = Match(uid=uid,
											match_id=match[0],
											draft_id=match[1],
											p1=match[2],
											p1_arch=match[3],
											p1_subarch=match[4],
											p2=match[5],
											p2_arch=match[6],
											p2_subarch=match[7],
											p1_roll=match[8],
											p2_roll=match[9],
											roll_winner=match[10],
											p1_wins=match[11],
											p2_wins=match[12],
											match_winner=match[13],
											format=match[14],
											limited_format=match[15],
											match_type=match[16],
											date=match[17],
											proc_dt=proc_dt)
							db.session.add(new_match)
							counts['new_matches'] += 1
					for game in parsed_data_inverted[1]:
						if Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first():
							existing = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
							existing.p2=game[2]
							existing.pd_selector=game[4]
							existing.pd_choice=game[5]
							existing.on_play=game[6]
							existing.on_draw=game[7]
							existing.p1_mulls=game[8]
							existing.p2_mulls=game[9]
							existing.turns=game[10]
							existing.proc_dt = proc_dt
							try:
								db.session.commit()
							except:
								db.session.rollback()
							counts['games_replaced'] += 1
						else:
							new_game = Game(uid=uid,
											match_id=game[0],
											p1=game[1],
											p2=game[2],
											game_num=game[3],
											pd_selector=game[4],
											pd_choice=game[5],
											on_play=game[6],
											on_draw=game[7],
											p1_mulls=game[8],
											p2_mulls=game[9],
											turns=game[10],
											game_winner=game[11],
											proc_dt=proc_dt)
							db.session.add(new_game)
							counts['new_games'] += 1
					for play in parsed_data_inverted[2]:
						if Play.query.filter_by(uid=uid, match_id=play[0], game_num=play[1], play_num=play[2]).first():
							continue
						new_play = Play(uid=uid,
										match_id=play[0],
										game_num=play[1],
										play_num=play[2],
										turn_num=play[3],
										casting_player=play[4],
										action=play[5],
										primary_card=play[6],
										target_list=play[7],
										opp_target=play[8],
										self_target=play[9],
										cards_drawn=play[10],
										attacker_list=play[11],
										attackers=play[12],
										active_player=play[13],
										non_active_player=play[14],
										proc_dt=proc_dt)
						db.session.add(new_play)
						counts['new_plays'] += 1
					for game in parsed_data_inverted[3]:
						if GameActions.query.filter_by(uid=uid, match_id=game[:-2], game_num=game[-1]).first():
							continue
						new_ga15 = GameActions(uid=uid,
											match_id=game[:-2],
											game_num=game[-1],
											game_actions='\n'.join(parsed_data_inverted[3][game][-15:]),
											proc_dt=proc_dt)
						db.session.add(new_ga15)
					try:
						db.session.commit()
					except:
						db.session.rollback()
				elif log_type == 'DraftLog':
					# DraftLog database operations
					debug_log(f"🔍 DRAFTLOG DB: Processing DraftLog database operations for {filename}")
					debug_log(f"🔍 DRAFTLOG DB: Number of drafts to process: {len(parsed_data[0])}")
					for draft in parsed_data[0]:
						debug_log(f"🔍 DRAFTLOG DB: Processing draft_id: {draft[0]}, hero: {draft[1]}")
						if Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first():
							debug_log(f"🔍 DRAFTLOG DB: Draft {draft[0]} already exists, updating...")
							existing = Draft.query.filter_by(uid=uid, draft_id=draft[0], hero=draft[1]).first()
							existing.player2 = draft[2]
							existing.player3 = draft[3]
							existing.player4 = draft[4]
							existing.player5 = draft[5]
							existing.player6 = draft[6]
							existing.player7 = draft[7]
							existing.player8 = draft[8]
							existing.draft_format = draft[11]
							existing.date = draft[12]
							existing.proc_dt = proc_dt
							Pick.query.filter_by(uid=uid, draft_id=draft[0]).delete()
							counts['drafts_replaced'] += 1
							try:
								db.session.commit()
							except:
								db.session.rollback()
						else:
							debug_log(f"🔍 DRAFTLOG DB: Creating new draft {draft[0]}")
							new_draft = Draft(uid=uid,
											draft_id=draft[0],
											hero=draft[1],
											player2=draft[2],
											player3=draft[3],
											player4=draft[4],
											player5=draft[5],
											player6=draft[6],
											player7=draft[7],
											player8=draft[8],
											match_wins=draft[9],
											match_losses=draft[10],
											draft_format=draft[11],
											date=draft[12],
											proc_dt=proc_dt)
							db.session.add(new_draft)
							counts['new_drafts'] += 1
							debug_log(f"🔍 DRAFTLOG DB: Added new draft {draft[0]} to session")
							
					debug_log(f"🔍 DRAFTLOG DB: Number of picks to process: {len(parsed_data[1])}")
					for pick in parsed_data[1]:
						if Pick.query.filter_by(uid=uid, draft_id=pick[0], pick_ovr=pick[4]).first():
							continue
						p = pick
						for index,i in enumerate(p):
							if i == 'NA':
								p[index] = ''
						new_pick = Pick(uid=uid,
										draft_id=pick[0],
										card=pick[1],
										pack_num=pick[2],
										pick_num=pick[3],
										pick_ovr=pick[4],
										avail1=p[5],
										avail2=p[6],
										avail3=p[7],
										avail4=p[8],
										avail5=p[9],
										avail6=p[10],
										avail7=p[11],
										avail8=p[12],
										avail9=p[13],
										avail10=p[14],
										avail11=p[15],
										avail12=p[16],
										avail13=p[17],
										avail14=p[18],
										proc_dt=proc_dt)
						db.session.add(new_pick)
						counts['new_picks'] += 1
					debug_log(f"🔍 DRAFTLOG DB: Added {counts['new_picks']} picks to session for this file")
					try:
						db.session.commit()
						debug_log(f"🔍 DRAFTLOG DB: Successfully committed {counts['new_drafts']} drafts and {counts['new_picks']} picks to database")
					except Exception as e:
						debug_log(f"🔍 DRAFTLOG DB: Failed to commit to database: {e}")
						db.session.rollback()
				if self.is_aborted():
					return 'TASK STOPPED'
			
			# TaskHistory creation and email operations (MOVED BEFORE build_cards_played_db)
			complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
			curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
			curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')
			
			new_task_history = TaskHistory(
				uid=data['user_id'],
				curr_username=data['username'],
				submit_date=submit_date,
				complete_date=complete_date,
				task_type='Import',
				error_code=error_code
			)
			db.session.add(new_task_history)
			try:
				db.session.commit()
			except:
				db.session.rollback()

			# Email operations (within Flask app context)
			debug_log("📧 LOAD REPORT: Starting email operations...")
			debug_log(f"📧 LOAD REPORT: Recipient email: {data['email']}")
			debug_log(f"📧 LOAD REPORT: Task ID: {new_task_history.task_id}")
			
			mail = app.extensions['mail']
			msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
			debug_log("📧 LOAD REPORT: Message object created")
			
			msg.html = f'''
		<h2 style="text-align: center">Load Report, Import GameLogs - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table>
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Records Loaded</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Updated</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['matches_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['games_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['plays_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['drafts_replaced']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['picks_replaced']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Skipped (Already Loaded)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Gamelogs Skipped (Removed)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 225px; min-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Gamelogs Skipped (Empty)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
				</tbody>
			</table>	
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.</p>
		</div>
		'''
			debug_log("📧 LOAD REPORT: About to send email...")
			try:
				mail.send(msg)
				debug_log("📧 EMAIL SUCCESS: Load report email sent successfully!")
			except Exception as e:
				debug_log(f"📧 EMAIL ERROR: Failed to send load report email: {e}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_SERVER={app.config.get('MAIL_SERVER')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USERNAME={app.config.get('MAIL_USERNAME')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_PORT={app.config.get('MAIL_PORT')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USE_TLS={app.config.get('MAIL_USE_TLS')}")
				debug_log(f"📧 EMAIL DEBUG: MAIL_USE_SSL={app.config.get('MAIL_USE_SSL')}")
			
			# Now run build_cards_played_db (after email is sent)
			build_cards_played_db(uid)
	
	except Exception as e:
		error_code = e

	return 'DONE'

@shared_task(bind=True, base=AbortableTask)
def process_revisions_from_app(self, data):
	counts = {
		'updated_matches':0,
		'updated_games':0,
		'updated_drafts':0
	}
	uid = data['user_id']
	drafts_to_update = []
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None

	# Get Flask app from Celery BEFORE processing files
	from app import create_app
	app = create_app()
	debug_log(f'App Created')
	with app.app_context():
		debug_log(f'App Context')
		try:
			debug_log(f'Starting Match Loop')
			debug_log(f'Match Loop Length: {len(data["all_data"][0])}')
			proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
			for match in data['all_data'][0]:
				if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
					debug_log(f'Updating Match: {match[0]} is in match table')
					existing_match = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
					if Draft.query.filter_by(uid=uid, draft_id=match[1]).first():
						existing_match.draft_id = match[1]
						drafts_to_update.append(match[1])
					existing_match.p1_arch = match[3]
					existing_match.p1_subarch = match[4]
					existing_match.p2_arch = match[6]
					existing_match.p2_subarch = match[7]
					existing_match.p1_wins = match[11]
					existing_match.p2_wins = match[12]
					existing_match.match_winner = match[13]
					existing_match.format = match[14]
					existing_match.limited_format = match[15]
					existing_match.match_type = match[16]
					existing_match.proc_dt = proc_dt
					merged_match = db.session.merge(existing_match)
					db.session.add(merged_match)
					counts['updated_matches'] += 1
			debug_log(f'Starting Game Loop')
			for game in data['all_data'][1]:
				if Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first():
					existing_game = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
					existing_game.game_winner = game[11]
					existing_game.proc_dt = proc_dt
					merged_game = db.session.merge(existing_game)
					db.session.add(merged_game)
					counts['updated_games'] += 1
			for draft_id in drafts_to_update:
				update_draft_wins(uid, data['username'], draft_id)
				counts['updated_drafts'] += 1

			try:
				debug_log(f'Committing to DB')
				db.session.commit()
			except:
				debug_log(f'DBError: {e}')
				db.session.rollback()
			debug_log(f'counts: {counts}')
			build_cards_played_db(uid)
		except Exception as e:
			debug_log(f'Error: {e}')
			error_code = e

		complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
		curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

		new_task_history = TaskHistory(
			uid=data['user_id'],
			curr_username=data['username'],
			submit_date=submit_date,
			complete_date=complete_date,
			task_type='Load Revisions From MTGO-Tracker',
			error_code=error_code
		)
		db.session.add(new_task_history)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		mail = app.extensions['mail']
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Import from MTGO-Tracker - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table>
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Records Loaded</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Updated</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Outdated*)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Ignored)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Duplicate)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
				</tbody>
			</table>
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.<br>
			*Outdated records were parsed using an outdated version of MTGO-Tracker.</p>
		</div>
		'''
		mail.send(msg)
		debug_log("📧 DEBUG: Email sent here")

	return 'DONE'

@shared_task(bind=True, base=AbortableTask)
def process_from_app(self, data):
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'updated_matches':0,
		'updated_games':0,
		'updated_plays':0,
		'updated_drafts':0,
		'updated_picks':0,
		'skipped_plays':0,
		'skipped_drafts':0,
		'skipped_picks':0,
		'gamelogs_skipped_digit':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0
	}
	uid = data['user_id']
	new_match_dict = {}
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None

	# Get Flask app from Celery BEFORE processing files
	from app import create_app
	app = create_app()
	debug_log(f'App Created')
	with app.app_context():
		debug_log(f'App Context')
		try:
			debug_log(f'Starting Match Loop')
			debug_log(f'Match Loop Length: {len(data["all_data"][0])}')
			proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
			for match in data['all_data'][0]:
				new_match_dict[match[0]] = False
				if match[0][0:12].isdigit():
					debug_log(f'Skipping Match: {match[0]} is digit')
					counts['gamelogs_skipped_digit'] += 1
					continue
				if Removed.query.filter_by(uid=uid, match_id=match[0]).first():
					debug_log(f'Skipping Match: {match[0]} is in removed table')
					counts['gamelogs_skipped_removed'] += 1
					continue
				if Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first():
					debug_log(f'Updating Match: {match[0]} is in match table')
					existing_match = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
					existing_match.p1_arch = match[3]
					existing_match.p1_subarch = match[4]
					existing_match.p2_arch = match[6]
					existing_match.p2_subarch = match[7]
					existing_match.p1_wins = match[11]
					existing_match.p2_wins = match[12]
					existing_match.match_winner = match[13]
					existing_match.format = match[14]
					existing_match.limited_format = match[15]
					existing_match.match_type = match[16]
					existing_match.proc_dt = proc_dt
					merged_match = db.session.merge(existing_match)
					db.session.add(merged_match)
					counts['updated_matches'] += 1
				else:
					debug_log(f'Adding Match: {match[0]} is not in match table')
					new_match = Match(uid=uid,
									match_id=match[0],
									draft_id=match[1],
									p1=match[2],
									p1_arch=match[3],
									p1_subarch=match[4],
									p2=match[5],
									p2_arch=match[6],
									p2_subarch=match[7],
									p1_roll=match[8],
									p2_roll=match[9],
									roll_winner=match[10],
									p1_wins=match[11],
									p2_wins=match[12],
									match_winner=match[13],
									format=match[14],
									limited_format=match[15],
									match_type=match[16],
									date=match[17],
									proc_dt=proc_dt)
					db.session.add(new_match)
					new_match_dict[match[0]] = True
					counts['new_matches'] += 1
			debug_log(f'Starting Game Loop')
			for game in data['all_data'][1]:
				if game[0][0:12].isdigit():
					continue
				if Removed.query.filter_by(uid=uid, match_id=game[0]).first():
					continue
				if Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first():
					existing_game = Game.query.filter_by(uid=uid, match_id=game[0], game_num=game[3], p1=game[1]).first()
					existing_game.game_winner = game[11]
					existing_game.proc_dt = proc_dt
					merged_game = db.session.merge(existing_game)
					db.session.add(merged_game)
					counts['updated_games'] += 1
				else:
					new_game = Game(uid=uid,
									match_id=game[0],
									p1=game[1],
									p2=game[2],
									game_num=game[3],
									pd_selector=game[4],
									pd_choice=game[5],
									on_play=game[6],
									on_draw=game[7],
									p1_mulls=game[8],
									p2_mulls=game[9],
									turns=game[10],
									game_winner=game[11],
									proc_dt=proc_dt)
					db.session.add(new_game)
					counts['new_games'] += 1
			debug_log(f'Starting Play Loop')
			for play in data['all_data'][2]:
				if play[0][0:12].isdigit():
					continue
				if new_match_dict[play[0]] == False:
					continue
				if Removed.query.filter_by(uid=uid, match_id=play[0]).first():
					continue
				if Play.query.filter_by(uid=uid, match_id=play[0], game_num=play[1], play_num=play[2]).first():
					counts['skipped_plays'] += 1
					continue
				else:
					new_play = Play(uid=uid,
										match_id=play[0],
										game_num=play[1],
										play_num=play[2],
										turn_num=play[3],
										casting_player=play[4],
										action=play[5],
										primary_card=play[6],
										target_list=play[7],
										opp_target=play[8],
										self_target=play[9],
										cards_drawn=play[10],
										attacker_list=play[11],
										attackers=play[12],
										active_player=play[13],
										non_active_player=play[14],
										proc_dt=proc_dt)
					db.session.add(new_play)
					counts['new_plays'] += 1
			debug_log(f'Starting Game Action Loop')
			for action in data['all_data'][3]:
				debug_log(f"🔍 DRAFTLOG DB: Processing action: {action[:-2]}")
				if action[0][0:12].isdigit():
					continue
				if new_match_dict[action[:-2]] == False:
					continue
				if Removed.query.filter_by(uid=uid, match_id=action[:-2]).first():
					continue
				if GameActions.query.filter_by(uid=uid, match_id=action[:-2], game_num=action[-1]).first():
					continue
				else:
					new_action = GameActions(uid=uid,
											match_id=action[:-2],
											game_num=action[-1],
											game_actions='\n'.join(data['all_data'][3][action][-15:]),
											proc_dt=proc_dt)
					db.session.add(new_action)
			debug_log(f'Starting Draft Loop')
			if len(data['drafts_table']) > 0:
				for draft in data['drafts_table']:
					if Removed.query.filter_by(uid=uid, match_id=draft[0]).first():
						continue
					if Draft.query.filter_by(uid=uid, draft_id=draft[0]).first():
						existing_draft = Draft.query.filter_by(uid=uid, draft_id=draft[0]).first()
						existing_draft.hero = draft[1]
						existing_draft.player2 = draft[2]
						existing_draft.player3 = draft[3]
						existing_draft.player4 = draft[4]
						existing_draft.player5 = draft[5]
						existing_draft.player6 = draft[6]
						existing_draft.player7 = draft[7]
						existing_draft.player8 = draft[8]
						existing_draft.match_wins = draft[9]
						existing_draft.match_losses = draft[10]
						existing_draft.draft_format = draft[11]
						existing_draft.date = draft[12]
						existing_draft.proc_dt = proc_dt
						merged_draft = db.session.merge(existing_draft)
						db.session.add(merged_draft)
						counts['updated_drafts'] += 1
					else:
						debug_log(f"🔍 DRAFTLOG DB: Creating new draft {draft[0]}")
						new_draft = Draft(uid=uid,
										draft_id=draft[0],
										hero=draft[1],
										player2=draft[2],
										player3=draft[3],
										player4=draft[4],
										player5=draft[5],
										player6=draft[6],
										player7=draft[7],
										player8=draft[8],
										match_wins=draft[9],
										match_losses=draft[10],
										draft_format=draft[11],
										date=draft[12],
										proc_dt=proc_dt)
						db.session.add(new_draft)
						counts['new_drafts'] += 1
			debug_log(f'Starting Pick Loop')
			for pick in data['picks_table']:
				if Removed.query.filter_by(uid=uid, match_id=pick[0]).first():
					continue
				p = pick
				for index,i in enumerate(p):
					if i == 'NA':
						p[index] = ''
				if Pick.query.filter_by(uid=uid, draft_id=pick[0], pick_ovr=pick[4]).first():
					counts['skipped_picks'] += 1
					continue
				else:
					new_pick = Pick(uid=uid,
									draft_id=pick[0],
									card=pick[1],
									pack_num=pick[2],
									pick_num=pick[3],
									pick_ovr=pick[4],
									avail1=p[5],
									avail2=p[6],
									avail3=p[7],
									avail4=p[8],
									avail5=p[9],
									avail6=p[10],
									avail7=p[11],
									avail8=p[12],
									avail9=p[13],
									avail10=p[14],
									avail11=p[15],
									avail12=p[16],
									avail13=p[17],
									avail14=p[18],
									proc_dt=proc_dt)
					db.session.add(new_pick)
					counts['new_picks'] += 1
			try:
				debug_log(f'Committing to DB')
				db.session.commit()
			except:
				debug_log(f'DBError: {e}')
				db.session.rollback()
			debug_log(f'counts: {counts}')
			build_cards_played_db(uid)
		except Exception as e:
			debug_log(f'Error: {e}')
			error_code = e

		complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
		curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

		new_task_history = TaskHistory(
			uid=data['user_id'],
			curr_username=data['username'],
			submit_date=submit_date,
			complete_date=complete_date,
			task_type='Import From MTGO-Tracker',
			error_code=error_code
		)
		db.session.add(new_task_history)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		mail = app.extensions['mail']
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Import from MTGO-Tracker - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table>
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Records Loaded</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Updated</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['updated_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Outdated*)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_digit']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Ignored)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 350px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Duplicate)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['skipped_picks']}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.<br>
			*Outdated records were parsed using an outdated version of MTGO-Tracker.</p>
		</div>
		'''
		mail.send(msg)
		debug_log("📧 DEBUG: Email sent here")

	return 'DONE'

@shared_task(bind=True, base=AbortableTask)
def reprocess_logs(self, data):
	counts = {
		'new_matches':0,
		'new_games':0,
		'new_plays':0,
		'new_drafts':0,
		'new_picks':0,
		'matches_updated':0,
		'drafts_updated':0,
		'matches_skipped_dupe':0,
		'games_skipped_dupe':0,
		'plays_skipped_dupe':0,
		'drafts_skipped_dupe':0,
		'picks_skipped_dupe':0,
		'gamelogs_skipped_error':0,
		'gamelogs_skipped_removed':0,
		'gamelogs_skipped_empty':0,
		'draftlogs_skipped_error':0,
		'draftlogs_skipped_removed':0,
		'draftlogs_skipped_empty':0,
		'total_gamelogs':0,
		'total_draftlogs':0,
	}
	game_errors = {}
	draft_errors = {}
	uid = data['user_id']
	submit_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
	error_code = None

	# Get Flask app from Celery BEFORE processing files
	from app import create_app
	app = create_app()
	
	with app.app_context():
		try:
			# Get list of files to process based on storage type
			files_to_process = []
			proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
			
			if not S3_ENABLED:  # Local file storage
				local_storage_dir = os.path.join('local-dev', 'data', 'uploads', str(uid))
				debug_log(f"🔍 REPROCESS: Looking for files in: {local_storage_dir}")
				debug_log(f"🔍 REPROCESS: Directory exists: {os.path.exists(local_storage_dir)}")
				if os.path.exists(local_storage_dir):
					all_files = os.listdir(local_storage_dir)
					debug_log(f"🔍 REPROCESS: Found {len(all_files)} total files: {all_files}")
					for filename in all_files:
						debug_log(f"🔍 REPROCESS: Processing file: {filename}")
						if filename.endswith('.meta'):  # Skip metadata files
							debug_log(f"🔍 REPROCESS: Skipping {filename} (metadata file)")
							continue
						
						local_file_path = os.path.join(local_storage_dir, filename)
						meta_file_path = local_file_path + '.meta'
						
						# Read metadata
						if os.path.exists(meta_file_path):
							with open(meta_file_path, 'r') as f:
								mtime = f.read().strip()
						else:
							mtime = '202301010000'  # Default fallback
						
						log_type = get_logtype_from_filename(filename)
						debug_log(f"🔍 REPROCESS: File {filename} detected as log_type: '{log_type}'")
						if log_type in ['GameLog', 'DraftLog']:
							debug_log(f"🔍 REPROCESS: Adding {filename} to files_to_process")
							files_to_process.append({
								'filename': filename,
								'path': local_file_path,
								'mtime': mtime,
								'storage_type': 'local',
								'log_type': log_type
							})
						else:
							debug_log(f"🔍 REPROCESS: Skipping {filename} - log_type '{log_type}' not in ['GameLog', 'DraftLog']")
				else:
					debug_log(f"🔍 REPROCESS: Local storage directory does not exist: {local_storage_dir}")
			else:  # S3 storage
				prefix = f"{S3_PREFIX}{uid}/"
				paginator = s3_client.get_paginator('list_objects_v2')
				for page in paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix):
					for obj in page.get('Contents', []):
						key = obj['Key']
						filename = key.split('/')[-1]
						if get_logtype_from_filename(filename) in ['GameLog', 'DraftLog']:
							try:
								head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=key)
								mtime = head.get('Metadata', {}).get('original_mod_time', '202301010000')
								files_to_process.append({
									'filename': filename,
									's3_key': key,
									'mtime': mtime,
									'storage_type': 's3',
									'log_type': get_logtype_from_filename(filename)
								})
							except ClientError:
								continue
			
			# Now process all files with unified logic
			debug_log(f"🔍 REPROCESS: Processing {len(files_to_process)} files")

			count_gamelogs = 0
			count_draftlogs = 0
			
			for file_info in files_to_process:
				filename = file_info['filename']
				mtime = file_info['mtime']
				log_type = file_info['log_type']

				debug_log(f'Filename: {filename}, mtime: {mtime}, log_type: {log_type}')
				
				# Read file content based on storage type
				if file_info['storage_type'] == 'local':
					with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
						initial = f.read().replace('\x00','')
				elif file_info['storage_type'] == 's3':
					obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_info['s3_key'])
					body = obj['Body'].read()
					initial = body.decode('utf-8', errors='ignore').replace('\r','').replace('\x00','')

				# Process based on log type
				if log_type == 'GameLog':
					count_gamelogs += 1
					debug_log(f'GameLog: {count_gamelogs}')
					fname = filename.split('_')[-1].split('.dat')[0]

					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['gamelogs_skipped_removed'] += 1
						debug_log(f'Skipping GameLog: {fname} - Removed')
						continue

					try:
						parsed_data = modo.get_all_data(initial,mtime,fname)
						parsed_data_inverted = modo.invert_join([[parsed_data[0]], parsed_data[1], parsed_data[2], parsed_data[3], parsed_data[4]])
						debug_log(f'Parsed Data: {fname}')
						counts['total_gamelogs'] += 1
						if len(parsed_data_inverted) > 3:
							debug_log(f'GameActions: {parsed_data_inverted[3]}')
					except Exception as error:
						counts['gamelogs_skipped_error'] += 1
						if str(error) in game_errors:
							game_errors[str(error)] += 1
						else:
							game_errors[str(error)] = 0
						debug_log(f'Skipping GameLog: {fname} - Error: {error}')
						continue

					if len(parsed_data_inverted[2]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, date=mtime, reason='Empty', proc_dt=proc_dt)
						db.session.add(newIgnore)
						counts['gamelogs_skipped_empty'] += 1
						debug_log(f'Skipping GameLog: {fname} - Empty')
						continue

					for match in parsed_data_inverted[0]:
						existing = Match.query.filter_by(uid=uid, match_id=match[0], p1=match[2]).first()
						if existing:
							# Update existing match, preserving user-revised columns
							# Delete related child records first
							Game.query.filter_by(uid=uid, match_id=match[0]).delete()
							Play.query.filter_by(uid=uid, match_id=match[0]).delete()
							GameActions.query.filter_by(uid=uid, match_id=match[0]).delete()
							
							# Update match, preserving user-revised columns
							existing.p2 = match[5]
							existing.p1_roll = match[8]
							existing.p2_roll = match[9]
							existing.roll_winner = match[10]
							existing.p1_wins = match[11]
							existing.p2_wins = match[12]
							existing.match_winner = match[13]
							existing.date = match[17]
							existing.proc_dt = proc_dt
							# Preserve user-revised columns: draft_id, p1_arch, p1_subarch, p2_arch, p2_subarch, format, limited_format, match_type
							counts['matches_updated'] += 1
						else:
							new_match = Match(uid=uid,
											match_id=match[0],
											draft_id=match[1],
											p1=match[2],
											p1_arch=match[3],
											p1_subarch=match[4],
											p2=match[5],
											p2_arch=match[6],
											p2_subarch=match[7],
											p1_roll=match[8],
											p2_roll=match[9],
											roll_winner=match[10],
											p1_wins=match[11],
											p2_wins=match[12],
											match_winner=match[13],
											format=match[14],
											limited_format=match[15],
											match_type=match[16],
											date=match[17],
											proc_dt=proc_dt)
							db.session.add(new_match)
							counts['new_matches'] += 1
					for game in parsed_data_inverted[1]:
						# Games are always new since we deleted all games for this match_id above
						new_game = Game(uid=uid,
										match_id=game[0],
										p1=game[1],
										p2=game[2],
										game_num=game[3],
										pd_selector=game[4],
										pd_choice=game[5],
										on_play=game[6],
										on_draw=game[7],
										p1_mulls=game[8],
										p2_mulls=game[9],
										turns=game[10],
										game_winner=game[11],
										proc_dt=proc_dt)
						db.session.add(new_game)
						counts['new_games'] += 1
					for play in parsed_data_inverted[2]:
						# Plays are always new since we deleted all plays for this match_id above
						new_play = Play(uid=uid,
										match_id=play[0],
										game_num=play[1],
										play_num=play[2],
										turn_num=play[3],
										casting_player=play[4],
										action=play[5],
										primary_card=play[6],
										target_list=play[7],
										opp_target=play[8],
										self_target=play[9],
										cards_drawn=play[10],
										attacker_list=play[11],
										attackers=play[12],
										active_player=play[13],
										non_active_player=play[14],
										proc_dt=proc_dt)
						db.session.add(new_play)
						counts['new_plays'] += 1
					for game in parsed_data_inverted[3]:
						# GameActions are always new since we deleted all game_actions for this match_id above
						new_ga15 = GameActions(uid=uid,
											match_id=game[:-2],
											game_num=game[-1],
											game_actions='\n'.join(parsed_data_inverted[3][game][-15:]),
											proc_dt=proc_dt)
						db.session.add(new_ga15)
					try:
						db.session.commit()
					except:
						db.session.rollback()

				elif log_type == 'DraftLog':
					count_draftlogs += 1
					debug_log(f'DraftLog: {count_draftlogs}')
					fname = filename.split('_')[-1].split('.draftlog')[0]

					if Removed.query.filter_by(uid=uid, match_id=fname).first():
						counts['draftlogs_skipped_removed'] += 1
						continue

					try:
						parsed_data = modo.parse_draft_log(filename, initial)
						counts['total_draftlogs'] += 1
					except Exception as error:
						counts['draftlogs_skipped_error'] += 1
						if str(error) in draft_errors:
							draft_errors[str(error)] += 1
						else:
							draft_errors[str(error)] = 0
						continue

					if len(parsed_data[1]) == 0:
						newIgnore = Removed(uid=uid, match_id=fname, date=mtime, reason='Empty', proc_dt=proc_dt)
						db.session.add(newIgnore)
						counts['draftlogs_skipped_empty'] += 1
						continue

					for draft in parsed_data[0]:
						existing = Draft.query.filter_by(uid=uid, draft_id=draft[0]).first()
						if existing:
							# Delete related picks before reprocessing
							Pick.query.filter_by(uid=uid, draft_id=draft[0]).delete()
							
							# Update existing draft with all new data
							existing.hero = draft[1]
							existing.player2 = draft[2]
							existing.player3 = draft[3]
							existing.player4 = draft[4]
							existing.player5 = draft[5]
							existing.player6 = draft[6]
							existing.player7 = draft[7]
							existing.player8 = draft[8]
							existing.match_wins = draft[9]
							existing.match_losses = draft[10]
							existing.draft_format = draft[11]
							existing.date = draft[12]
							existing.proc_dt = proc_dt
							counts['drafts_updated'] += 1
						else:
							new_draft = Draft(uid=uid,
											draft_id=draft[0],
											hero=draft[1],
											player2=draft[2],
											player3=draft[3],
											player4=draft[4],
											player5=draft[5],
											player6=draft[6],
											player7=draft[7],
											player8=draft[8],
											match_wins=draft[9],
											match_losses=draft[10],
											draft_format=draft[11],
											date=draft[12],
											proc_dt=proc_dt)
							db.session.add(new_draft)
							counts['new_drafts'] += 1
						update_draft_wins(uid, data['username'], draft[0])

					for pick in parsed_data[1]:
						# Picks are always new since we deleted all picks for this draft_id above
						p = pick
						for index,i in enumerate(p):
							if i == 'NA':
								p[index] = ''
						new_pick = Pick(uid=uid,
										draft_id=pick[0],
										card=pick[1],
										pack_num=pick[2],
										pick_num=pick[3],
										pick_ovr=pick[4],
										avail1=p[5],
										avail2=p[6],
										avail3=p[7],
										avail4=p[8],
										avail5=p[9],
										avail6=p[10],
										avail7=p[11],
										avail8=p[12],
										avail9=p[13],
										avail10=p[14],
										avail11=p[15],
										avail12=p[16],
										avail13=p[17],
										avail14=p[18],
										proc_dt=proc_dt)
						db.session.add(new_pick)
						counts['new_picks'] += 1
					try:
						db.session.commit()
					except:
						db.session.rollback()
				if self.is_aborted():
					return 'TASK STOPPED'
			build_cards_played_db(uid)
		except Exception as e:
			debug_log(f'Error: {e}')
			error_code = e

		complete_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		curr_date = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).strftime('%Y-%m-%d')
		curr_time = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')).time().strftime('%H:%M')

		new_task_history = TaskHistory(
			uid=data['user_id'],
			curr_username=data['username'],
			submit_date=submit_date,
			complete_date=complete_date,
			task_type='Re-Process',
			error_code=error_code
		)
		db.session.add(new_task_history)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		mail = app.extensions['mail']
		msg = Message(f'MTGO-DB Load Report #{new_task_history.task_id}', sender=app.config.get('MAIL_USERNAME'), recipients=[data['email']])
		msg.html = f'''
		<h2 style="text-align: center">Load Report, Re-Processing Data - #{new_task_history.task_id}<br></h2>
		<h3 style="text-align: center">Completed: {curr_date} at {curr_time}<h3><br><br>

		<div style="display: flex; justify-content: center;">
			<table style="text-align: center">
				<thead>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Load Result</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Matches</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Games</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Plays</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Drafts</th>
						<th style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">Draft Picks</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Reprocessed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_gamelogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['total_draftlogs']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Matches Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_matches']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_drafts']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Games Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_games']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Plays Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_plays']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">New Draft Picks Processed</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['new_picks']}</td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Removed)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_removed']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Empty)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_empty']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Files Skipped (Errors)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['gamelogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['draftlogs_skipped_error']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center"></td>
					</tr>
					<tr>
						<th style="font-size: 14pt; max-width: 300px; min-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left">Records Skipped (Duplicates)</th>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['matches_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['games_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['plays_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['drafts_skipped_dupe']}</td>
						<td style="font-size: 14pt; max-width: 125px; min-width: 125px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center">{counts['picks_skipped_dupe']}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div style="display: flex; justify-content: center;">
			<p style="text-align: center; font-style: italic;">Note: Two records are loaded and stored for each Match and Game.
		</div>
		'''
		mail.send(msg)
		debug_log("📧 DEBUG: Email sent here")

	return 'DONE'

@views.route('/tasks', methods=['GET'])
@login_required
def task_monitor():
	"""Monitor Celery background tasks"""
	try:
		# Get recent task history from database - this is reliable
		recent_tasks = TaskHistory.query.filter_by(uid=current_user.uid).order_by(desc(TaskHistory.submit_date)).limit(10).all()
		
		# For now, skip live Celery monitoring to avoid app context issues
		# Focus on database task history which is most useful
		task_data = {
			'active': {},
			'scheduled': {},
			'reserved': {},
			'recent_history': [task.as_dict() for task in recent_tasks] if recent_tasks else [],
			'info': 'Live task monitoring coming soon. For now, view recent task history below.'
		}
		
		return render_template('task_monitor.html', user=current_user, task_data=task_data)
		
	except Exception as e:
		debug_log(f"Error in task monitor: {e}")
		# Fallback with error message
		task_data = {
			'active': {},
			'scheduled': {},
			'reserved': {},
			'recent_history': [],
			'error': f'Error loading task history: {str(e)}'
		}
		
		return render_template('task_monitor.html', user=current_user, task_data=task_data)

@views.route('/update_vars', methods=['GET'])
@login_required
def update_vars():
	global options, multifaced, all_decks
	if (current_user.uid != 1):
		return 'Forbidden', 403
	try:
		# Force reload by setting to None first
		options = None
		multifaced = None
		all_decks = None
		# Now load fresh data
		ensure_data_loaded()
	except Exception as e:
		flash(f'Error loading auxiliary files: {e}', category='error')
	flash('Loaded all auxiliary files successfully.', category='success')
	return render_template('index.html', user=current_user)

@views.route('/send_confirmation_email', methods=['POST'])
def send_confirmation_email():
	inputs = [request.form.get('confirm_email'), request.form.get('confirm_pwd')]

	if (not inputs[0]) or (not inputs[1]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)

	user = Player.query.filter_by(email=inputs[0]).first()
	if not user:
		flash('Email not found.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)
	if not check_password_hash(user.pwd, inputs[1]):
		flash('Email/Password combination not found.', category='error')
		return render_template('login.html', user=current_user, inputs=inputs, not_confirmed=True)
	if user.is_confirmed:
		flash('User has already been confirmed.', category='error')
		login_user(user, remember=True)
		return redirect(url_for('views.profile'))
	else:
		token = s.dumps(inputs[0], salt=current_app.config.get("EMAIL_CONFIRMATION_SALT"))
		mail = current_app.extensions['mail'] 
		with current_app.app_context():
			msg = Message('MTGO-Tracker - Email Confirmation', sender=current_app.config.get('MAIL_USERNAME'), recipients=[inputs[0]])
			link = url_for('views.confirm_email', token=token, _external=True)
			msg.body = 'Click the following link to confirm your email:\n\n{}'.format(link)
			mail.send(msg)

		flash(f'New confirmation email has been sent (may need to check spam/junk folder).', category='success')
		return render_template('index.html', user=current_user)

@views.route('/email', methods=['POST'])
def email():
	inputs = [request.form.get('email'), request.form.get('pwd'), request.form.get('pwd_confirm'), request.form.get('hero')]

	if (not inputs[0]) or (not inputs[1]) or (not inputs[2]) or (not inputs[3]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('register.html', user=current_user, inputs=inputs)
	elif inputs[1] != inputs[2]:
		flash(f'Passwords do not match.', category='error')
		return render_template('register.html', user=current_user, inputs=inputs)
	else:
		user = Player.query.filter_by(email=inputs[0]).first()
		if user:
			flash(f'Account with this email address already exists.', category='error')
			return render_template('register.html', user=current_user, inputs=inputs)
		new_user = Player(email=inputs[0], 
						  pwd=generate_password_hash(inputs[1]), 
						  username=inputs[3],
						  created_on=datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific')),
						  is_admin=False,
						  is_confirmed=False,
						  confirmed_on=None)
		db.session.add(new_user)
		try:
			db.session.commit()
		except:
			db.session.rollback()

		email = request.form['email']
		token = s.dumps(email, salt=current_app.config.get("EMAIL_CONFIRMATION_SALT"))

		mail = current_app.extensions['mail'] 
		with current_app.app_context():
			msg = Message('MTGO-Tracker - Email Confirmation', sender=current_app.config.get('MAIL_USERNAME'), recipients=[email])
			link = url_for('views.confirm_email', token=token, _external=True)
			msg.body = 'Click the following link to confirm your email:\n\n{}'.format(link)
			mail.send(msg)

		logout_user()
		flash(f'User account created. Email confirmation sent (may need to check spam/junk folder).', category='success')
		return redirect(url_for('views.index'))

@views.route('/reset_pwd', methods=['POST'])
def reset_pwd():
	email = request.form['reset_email']

	if not email:
		flash(f'Please fill in all fields.', category='error')
		return render_template('login.html', user=current_user, inputs=['',''])
	user = Player.query.filter_by(email=email).first()
	if not user:
		flash(f'Account with this email address does not exist.', category='error')
		return render_template('login.html', user=current_user, inputs=['',''])

	token = s.dumps(email, salt=current_app.config.get('RESET_PASSWORD_SALT'))

	mail = current_app.extensions['mail'] 
	with current_app.app_context():
		msg = Message('MTGO-Tracker - Password Reset', sender=current_app.config.get('MAIL_USERNAME'), recipients=[email])
		link = url_for('views.reset_email', token=token, _external=True)
		msg.body = 'Click the following link to reset your password:\n\n{}'.format(link)
		mail.send(msg)

	flash(f'Reset Password email sent (may need to check spam/junk folder).', category='success')
	return render_template('login.html', user=current_user, inputs=[email,""], not_confirmed=False)

@views.route('/confirm_email/<token>')
def confirm_email(token):
	try:
		email = s.loads(token, salt=current_app.config.get('EMAIL_CONFIRMATION_SALT'), max_age=3600)
		user = Player.query.filter_by(email=email).first()
		if user is None:
			return "User not found"
		user.is_confirmed = True
		user.confirmed_on = datetime.datetime.now()
		try:
			db.session.commit()
		except:
			db.session.rollback()
		login_user(user, remember=True)
		flash('Thank you for confirming your email. Welcome to your MTGO-Tracker profile page.', category="success")
		return redirect(url_for('views.profile'))
	except SignatureExpired:
		flash('Email confirmation link has expired.', category='error')
		return redirect(url_for('views.index'))
	except BadTimeSignature:
		flash('The token is not correct.', category='error')
		return redirect(url_for('views.index'))

@views.route('/reset_email/<token>')
def reset_email(token):
	try:
		email = s.loads(token, salt=current_app.config.get('RESET_PASSWORD_SALT'), max_age=3600)
		user = Player.query.filter_by(email=email).first()
		if user is None:
			flash('User not found.', category='error')
			return redirect(url_for('views.index'))
		return render_template('resetpwd.html', user=current_user, inputs=[email])
	except SignatureExpired:
		flash('Reset Password link has expired.', category='error')
		return redirect(url_for('views.index'))
	except BadTimeSignature:
		flash('The token is not correct.', category='error')
		return redirect(url_for('views.index'))

@views.route('/change_pwd', methods=['POST'])
def change_pwd():
	inputs = [request.form.get('email'), request.form.get('new_pwd'), request.form.get('new_pwd_confirm')]

	user = Player.query.filter_by(email=inputs[0]).first()
	if user is None:
		flash('User not found.', category='error')
		return redirect(url_for('views.index'))
	if (not inputs[0]) or (not inputs[1]) or (not inputs[2]):
		flash(f'Please fill in all fields.', category='error')
		return render_template('resetpwd.html', user=current_user, inputs=[inputs[1]])
	elif inputs[1] != inputs[2]:
		flash(f'Passwords do not match.', category='error')
		return render_template('resetpwd.html', user=current_user, inputs=[inputs[1]])
	else:
		user.pwd = generate_password_hash(inputs[1])
		try:
			db.session.commit()
		except:
			db.session.rollback()
		login_user(user, remember=True)
		flash(f'Password updated successfully.', category='success')
		return redirect(url_for('views.profile'))

@views.route('/')
def index():
	return render_template('index.html', user=current_user)

@views.route('/register')
def register():
	if current_user.is_authenticated:
		return redirect(url_for('views.profile'))
	
	inputs = ['', '', '', '']
	return render_template('register.html', user=current_user, inputs=inputs)

@views.route('/login', methods=['GET', 'POST'])
def login():
	if current_user.is_authenticated:
		return redirect(url_for('views.profile'))
	
	if request.method == 'POST':
		login_email = request.form.get('login_email')
		login_pwd = request.form.get('login_pwd')
		user = Player.query.filter_by(email=login_email).first()
		if (not login_email) or (not login_pwd):
			flash(f'Please fill in all fields.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

		if not user:
			flash('Email not found.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

		if check_password_hash(user.pwd, login_pwd):
			if user.is_confirmed == False:
				flash('Email has not been confirmed.', category='error')
				return render_template('login.html', user=current_user, inputs=[login_email, login_pwd], not_confirmed=True)
			login_user(user, remember=True)
			flash('Logged in.', category='success')
			return redirect(url_for('views.profile'))
		else:
			flash('Email/Password combination not found.', category='error')
			return render_template('login.html', user=current_user, inputs=[login_email, login_pwd])

	return render_template('login.html', user=current_user, inputs=['',''])

@views.route('/logout')
@login_required
def logout():
	logout_user()
	flash('User logged out.', category='error')
	return redirect(url_for('views.index'))

@views.route('/load', methods=['POST'])
@login_required
def load():
	if ('file' not in request.files):
		flash('No file uploaded.', category='error')
		return redirect(url_for('views.index'))
	uploaded_file = request.files['file']
	if (uploaded_file.filename == ''):
		flash('No file selected.', category='error')
		return redirect(url_for('views.index'))

	file_stream = io.BytesIO(uploaded_file.read())

	task = process_logs.delay({'email':current_user.email, 'file_stream':file_stream.getvalue(), 'user_id':current_user.uid, 'username':current_user.username})

	flash(f'Your data is now being processed. This may take several minutes depending on the number of files. A Load Report will be emailed upon completion.', category='success')
	return redirect(url_for('views.index'))

@views.route('/load_from_app', methods=['POST'])
@login_required
def load_from_app():
	files = request.files.getlist('folder')
	process_total = 0

	all_data = []
	drafts_table = []
	picks_table = []

	for i in files:
		if not i:
			continue
		filename = i.filename.split('/')[-1]
		debug_log(f'Filename: {filename}')
		if (filename not in ['ALL_DATA', 'DRAFTS_TABLE', 'PICKS_TABLE']):
			continue
		if filename == 'ALL_DATA':
			try:
				all_data = pickle.loads(i.read())
				all_data = modo.invert_join(all_data)
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(all_data[0])
			process_total += len(all_data[1])
			process_total += len(all_data[2])
			process_total += len(all_data[3])
			debug_log(f'All Data: {len(all_data[0])} matches, {len(all_data[1])} games, {len(all_data[2])} plays, {len(all_data[3])} gameactions?')
		elif filename == 'DRAFTS_TABLE':
			try:
				drafts_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(drafts_table)
			debug_log(f'Drafts Table: {len(drafts_table)} drafts')
		elif filename == 'PICKS_TABLE':
			try:
				picks_table = pickle.loads(i.read())
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(picks_table)
			debug_log(f'Picks Table: {len(picks_table)} picks')

	if (len(all_data) == 0) and (len(drafts_table) == 0) and (len(picks_table) == 0):
		flash('No MTGO-Tracker save data was found.', 'error')
		return redirect(url_for('views.index'))

	task = process_from_app.delay({'all_data':all_data, 'drafts_table':drafts_table, 'picks_table':picks_table, 'user_id':current_user.uid, 'username':current_user.username, 'email':current_user.email})

	flash(f'MTGO-Tracker save data is being processed. A Load Report will be emailed upon completion.', category='success')
	return redirect(url_for('views.index'))

@views.route('/load_revisions_from_app', methods=['POST'])
@login_required
def load_revisions_from_app():
	files = request.files.getlist('folder')
	process_total = 0

	all_data = []

	for i in files:
		if not i:
			continue
		filename = i.filename.split('/')[-1]
		debug_log(f'Filename: {filename}')
		if (filename not in ['ALL_DATA']):
			continue
		if filename == 'ALL_DATA':
			try:
				all_data = pickle.loads(i.read())
				all_data = modo.invert_join(all_data)
			except pickle.UnpicklingError:
				flash(f'Unable to read file: {i.filename}.', category='error')
				return redirect(url_for('views.index'))
			process_total += len(all_data[0])
			process_total += len(all_data[1])
			process_total += len(all_data[2])
			process_total += len(all_data[3])
			debug_log(f'All Data: {len(all_data[0])} matches, {len(all_data[1])} games, {len(all_data[2])} plays, {len(all_data[3])} gameactions')

	if (len(all_data) == 0):
		flash('No MTGO-Tracker save data was found.', 'error')
		return redirect(url_for('views.index'))

	task = process_revisions_from_app.delay({'all_data':all_data, 'user_id':current_user.uid, 'username':current_user.username, 'email':current_user.email})

	flash(f'MTGO-Tracker save data is being analyzed. A Load Report will be emailed upon completion.', category='success')
	return redirect(url_for('views.index'))

@views.route('/table/<table_name>/<page_num>')
@login_required
def table(table_name, page_num):
	limited_formats = get_input_options().get('Limited Formats', [])
	try:
		page_num = int(page_num)
	except ValueError:
		flash(f'ValueError: Probably typed the address incorrectly.', category='error')
		return render_template('tables.html', user=current_user, table_name=table_name, column_widths=get_column_widths(table_name), limited_formats=limited_formats)

	if table_name.lower() == 'matches':
		# Uncomment to display fully inverted Matches table.
		#pages = math.ceil(Match.query.filter_by(uid=current_user.uid).count()/page_size)
		pages = math.ceil(Match.query.filter_by(uid=current_user.uid, p1=current_user.username).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		#table = Match.query.filter_by(uid=current_user.uid).order_by(Match.match_id).limit(page_size*int(page_num)).all()
		table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Match.date)).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'games':
		pages = math.ceil(Game.query.filter_by(uid=current_user.uid, p1=current_user.username).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Game.match_id), Game.game_num).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'plays':
		pages = math.ceil(Play.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Play.query.filter_by(uid=current_user.uid).order_by(desc(Play.match_id), Play.game_num, Play.play_num).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'drafts':
		pages = math.ceil(Draft.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Draft.query.filter_by(uid=current_user.uid).order_by(desc(Draft.date)).limit(page_size*int(page_num)).all()
	elif table_name.lower() == 'picks':
		pages = math.ceil(Pick.query.filter_by(uid=current_user.uid).count()/page_size)
		if (int(page_num) < 1) or (int(page_num) > pages):
			page_num = 0
		table = Pick.query.filter_by(uid=current_user.uid).order_by(desc(Pick.draft_id), Pick.pick_ovr).limit(page_size*int(page_num)).all()

	if pages == int(page_num):
		table = table[(int(page_num)-1)*page_size:]
	else:
		table = table[-page_size:]

	page_num = int(page_num)

	return render_template('tables.html', user=current_user, table_name=table_name, table=table, page_num=page_num, pages=pages, column_widths=get_column_widths(table_name), limited_formats=limited_formats)

@views.route('/ignored', methods=['GET'])
@login_required
def ignored():
	table = Removed.query.filter_by(uid=current_user.uid).order_by(Removed.match_id).all()
	if len(table) == 0:
		return redirect(url_for('views.index'))
	return render_template('tables.html', user=current_user, table_name='ignored', table=table, column_widths=get_column_widths('ignored'))

@views.route('/table/<table_name>/<row_id>/<game_num>')
@login_required
def table_drill(table_name, row_id, game_num):
	if table_name.lower() == 'games':
		table = Game.query.filter_by(uid=current_user.uid, match_id=row_id, p1=current_user.username).order_by(Game.match_id).all() 
	elif table_name.lower() == 'plays':
		table = Play.query.filter_by(uid=current_user.uid, match_id=row_id, game_num=game_num).order_by(Play.match_id).all()  
	elif table_name.lower() == 'picks':
		table = Pick.query.filter_by(uid=current_user.uid, draft_id=row_id).order_by(Pick.pick_ovr).all()  

	return render_template('tables.html', user=current_user, table_name=table_name, table=table, column_widths=get_column_widths(table_name))

# New cleaner API routes for Game Winner functionality
@views.route('/api/game-winner/next', methods=['GET'])
@login_required
def api_game_winner_next():
	"""Get the next game that needs a winner assigned"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Query for games with missing winners
		na_query = Game.query.filter_by(
			uid=current_user.uid, 
			game_winner='NA', 
			p1=current_user.username
		).join(
			Match, 
			(Game.uid == Match.uid) & 
			(Game.match_id == Match.match_id) & 
			(Game.p1 == Match.p1)
		).add_entity(Match)

		if na_query.first() is None:
			return jsonify({'hasGames': False})

		# Find first game with game actions
		for game, match in na_query.order_by(asc(Match.date), asc(Game.game_num)).all():
			game_actions_record = GameActions.query.filter_by(
				uid=current_user.uid, 
				match_id=match.match_id, 
				game_num=game.game_num
			).first()
			
			if game_actions_record:
				ga = game_actions_record.game_actions.split('\n')[-15:]
				
				# Format game actions (handle @[...@] formatting)
				formatted_actions = []
				for action in ga:
					if action.count('@[') != action.count('@]'):
						formatted_actions.append(action)
						continue
					
					formatted = action
					for _ in range(action.count('@[')):
						formatted = formatted.replace('@[', '<strong>', 1).replace('@]', '</strong>', 1)
					formatted_actions.append(formatted)
				
				# Prepare response data
				game_data = game.as_dict()
				game_data.update({
					'date': match.date,
					'game_actions': formatted_actions,
					'hasGames': True
				})
				
				return jsonify(game_data)
		
		return jsonify({'hasGames': False})
		
	except Exception as e:
		debug_log(f"Error in api_game_winner_next: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/game-winner/update', methods=['POST'])
@login_required  
def api_game_winner_update():
	"""Update a game winner and return the next game"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		game_num = data.get('game_num')
		winner = data.get('winner')  # 'P1', 'P2', or 'skip'
		p1 = data.get('p1')
		p2 = data.get('p2')
		
		if not all([match_id, game_num, winner]):
			return jsonify({'error': 'Missing required fields'}), 400
		
		# Update game winner if not skipped
		if winner != 'skip':
			games = Game.query.filter_by(
				match_id=match_id, 
				game_num=game_num, 
				uid=current_user.uid
			).all()
			
			matches = Match.query.filter_by(
				match_id=match_id, 
				uid=current_user.uid
			).all()
			
			draft_id = 'NA'
			
			# Determine actual winner name
			if winner == 'P1':
				game_winner = p1
			elif winner == 'P2':
				game_winner = p2
			else:
				game_winner = '0'
			
			# Update games
			for game in games:
				if game.game_winner == 'NA':
					if game.p1 == game_winner:
						game.game_winner = 'P1'
					elif game.p2 == game_winner:
						game.game_winner = 'P2'
			
			# Update matches
			for match in matches:
				draft_id = match.draft_id
				if match.p1 == game_winner:
					match.p1_wins += 1
				elif match.p2 == game_winner:
					match.p2_wins += 1
				
				# Update match winner
				if match.p1_wins > match.p2_wins:
					match.match_winner = 'P1'
				elif match.p2_wins > match.p1_wins:
					match.match_winner = 'P2'
				else:
					match.match_winner = 'NA'
			
			# Delete GameActions records for this game
			GameActions.query.filter_by(
				uid=current_user.uid,
				match_id=match_id,
				game_num=game_num
			).delete()
			
			# Update draft win/loss records
			update_draft_win_loss(
				uid=current_user.uid, 
				username=current_user.username, 
				draft_id=draft_id
			)
			
			try:
				db.session.commit()
			except Exception as e:
				db.session.rollback()
				debug_log(f"Error committing game winner update: {str(e)}")
				return jsonify({'error': 'Failed to update database'}), 500
		
		# Find next game
		current_match_date = Match.query.filter_by(
			match_id=match_id, 
			uid=current_user.uid
		).first().date
		
		rem_games = Game.query.filter_by(
			uid=current_user.uid, 
			game_winner='NA', 
			p1=current_user.username
		).join(
			Match, 
			(Game.uid == Match.uid) & 
			(Game.match_id == Match.match_id) & 
			(Game.p1 == Match.p1)
		).add_entity(Match).filter(
			Match.date >= current_match_date
		).order_by(asc(Match.date), asc(Game.game_num))
		
		# Look for next game after current one
		current_found = False
		for game, match in rem_games.all():
			# Find current game first, then return the next one
			if (match.match_id == match_id) and (game.game_num == int(game_num)):
				current_found = True
				continue
			
			# If we haven't found the current game yet, skip this one
			if not current_found:
				continue
			
			game_actions_record = GameActions.query.filter_by(
				uid=current_user.uid, 
				match_id=match.match_id, 
				game_num=game.game_num
			).first()
			
			if game_actions_record:
				ga = game_actions_record.game_actions.split('\n')[-15:]
				
				# Format game actions
				formatted_actions = []
				for action in ga:
					if action.count('@[') != action.count('@]'):
						formatted_actions.append(action)
						continue
					
					formatted = action
					for _ in range(action.count('@[')):
						formatted = formatted.replace('@[', '<strong>', 1).replace('@]', '</strong>', 1)
					formatted_actions.append(formatted)
				
				# Prepare next game data
				next_game_data = game.as_dict()
				next_game_data.update({
					'date': match.date,
					'game_actions': formatted_actions
				})
				
				return jsonify({
					'hasNextGame': True,
					'nextGame': next_game_data
				})
		
		# No more games found
		return jsonify({'hasNextGame': False})
		
	except Exception as e:
		debug_log(f"Error in api_game_winner_update: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

# New cleaner API routes for Draft ID functionality
@views.route('/api/draft-id/next', methods=['GET'])
@login_required
def api_draft_id_next():
	"""Get the next limited match that needs a draft_id assigned"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	global multifaced
	if multifaced is None:
		try:
			multifaced = get_multifaced_cards()
		except Exception as e:
			debug_log(f"Warning: Could not load multifaced cards: {e}")
			multifaced = {}
	
	def threshold_met(pick_list, played_list):
		if not pick_list or not played_list:
			return 0
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	try:
		# Query for limited matches with missing draft_id
		limited_matches = Match.query.filter_by(
			uid=current_user.uid, 
			draft_id='NA', 
			p1=current_user.username
		).filter(
			Match.format.in_(['Cube', 'Booster Draft'])
		).order_by(asc(Match.date))
		
		first_match = limited_matches.first()
		
		# Find a match with valid card data and possible draft associations
		while first_match:
			# Get cards played in this match
			lands = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=first_match.match_id, 
				casting_player=first_match.p1, 
				action='Land Drop'
			).order_by(Play.primary_card)]
			
			nb_lands = [i for i in lands if i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']]
			spells = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=first_match.match_id, 
				casting_player=first_match.p1, 
				action='Casts'
			).order_by(Play.primary_card)]

			# Clean card sets
			nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
			lands = list(modo.clean_card_set(set(lands), multifaced))
			spells = list(modo.clean_card_set(set(spells), multifaced))

			# Find possible draft IDs based on card overlap
			draft_ids_100 = []
			draft_ids_80 = []
			draft_ids_all = []

			for draft in Draft.query.filter_by(uid=current_user.uid).filter(
				Draft.date < first_match.date
			).order_by(desc(Draft.date)).all():
				picks = [pick.card for pick in Pick.query.filter_by(
					uid=current_user.uid, 
					draft_id=draft.draft_id
				)]
				picks = list(modo.clean_card_set(set(picks), multifaced))
				pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
				
				if pick_perc == 100:
					draft_ids_100.append(draft.draft_id)
				elif pick_perc >= 80:
					draft_ids_80.append(draft.draft_id)
				else:
					draft_ids_all.append(draft.draft_id)
			
			# Prioritize better matches
			possible_draft_ids = []
			if len(draft_ids_100) > 0:
				possible_draft_ids = draft_ids_100
			elif len(draft_ids_80) > 0:
				possible_draft_ids = draft_ids_80
			else:
				possible_draft_ids = draft_ids_all

			if len(possible_draft_ids) > 0:
				# Found a match with possible associations
				match_data = first_match.as_dict()
				match_data.update({
					'lands': sorted(list(set(lands))),
					'spells': sorted(list(set(spells))),
					'possible_draft_ids': possible_draft_ids,
					'hasMatches': True
				})
				
				return jsonify(match_data)

			# Try next match
			limited_matches = limited_matches.filter(Match.date > first_match.date).order_by(Match.date)
			first_match = limited_matches.first()
		
		# No matches found
		return jsonify({'hasMatches': False})
		
	except Exception as e:
		debug_log(f"Error in api_draft_id_next: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/draft-id/update', methods=['POST'])
@login_required  
def api_draft_id_update():
	"""Update a match with draft_id and return the next match"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	global multifaced
	if multifaced is None:
		try:
			multifaced = get_multifaced_cards()
		except Exception as e:
			debug_log(f"Warning: Could not load multifaced cards: {e}")
			multifaced = {}
	
	def threshold_met(pick_list, played_list):
		if not pick_list or not played_list:
			return 0
		condition_met = sum(1 for i in played_list if i in pick_list)
		perc = (condition_met / len(played_list)) * 100
		return perc
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		draft_id = data.get('draft_id')
		skip = data.get('skip', False)
		
		if not match_id:
			return jsonify({'error': 'Missing match_id'}), 400
		
		# Update match with draft_id if not skipped
		if not skip and draft_id:
			matches = Match.query.filter_by(
				uid=current_user.uid, 
				match_id=match_id
			).all()
			
			for match in matches:
				match.draft_id = draft_id
			
			# Update draft match statistics
			match_wins = 0
			match_losses = 0
			associated_matches = Match.query.filter_by(
				uid=current_user.uid, 
				draft_id=draft_id, 
				p1=current_user.username
			)
			
			for match in associated_matches:
				if match.p1_wins > match.p2_wins:
					match_wins += 1
				elif match.p2_wins > match.p1_wins:
					match_losses += 1
			
			draft = Draft.query.filter_by(
				uid=current_user.uid, 
				draft_id=draft_id
			).first()
			
			if draft:
				draft.match_wins = match_wins
				draft.match_losses = match_losses
			
			try:
				db.session.commit()
			except Exception as e:
				db.session.rollback()
				debug_log(f"Error committing draft ID update: {str(e)}")
				return jsonify({'error': 'Failed to update database'}), 500
		
		# Find next match using sequential approach (same as GameWinner)
		current_match_date = Match.query.filter_by(
			match_id=match_id, 
			uid=current_user.uid
		).first().date
		
		# Query for remaining limited matches (include current date for sequential search)
		remaining_matches = Match.query.filter_by(
			uid=current_user.uid, 
			draft_id='NA', 
			p1=current_user.username
		).filter(
			Match.format.in_(['Cube', 'Booster Draft'])
		).filter(
			Match.date >= current_match_date  # Include current date
		).order_by(Match.date)
		
		# Look for next match after current one using sequential logic
		current_found = False
		next_match = None
		for match in remaining_matches.all():
			# Find current match first, then return the next one
			if match.match_id == match_id:
				current_found = True
				continue
			
			# If we haven't found the current match yet, skip this one
			if not current_found:
				continue
			
			# This is the next match after current
			next_match = match
			break
		
		# Find next match with valid card data and possible associations
		while next_match:
			# Get cards played in this match
			lands = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=next_match.match_id, 
				casting_player=next_match.p1, 
				action='Land Drop'
			).order_by(Play.primary_card)]
			
			nb_lands = [i for i in lands if i not in ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']]
			spells = [play.primary_card for play in Play.query.filter_by(
				uid=current_user.uid, 
				match_id=next_match.match_id, 
				casting_player=next_match.p1, 
				action='Casts'
			).order_by(Play.primary_card)]

			# Clean card sets
			nb_lands = list(modo.clean_card_set(set(nb_lands), multifaced))
			lands = list(modo.clean_card_set(set(lands), multifaced))
			spells = list(modo.clean_card_set(set(spells), multifaced))

			# Find possible draft IDs based on card overlap
			debug_log(f"next_match.match_id: {next_match.match_id}")
			debug_log(f"next_match.date: {next_match.date}")
			debug_log(f"nb_lands: {nb_lands}")
			debug_log(f"spells: {spells}")
			draft_ids_100 = []
			draft_ids_80 = []
			draft_ids_all = []

			for draft in Draft.query.filter_by(uid=current_user.uid).filter(
				Draft.date < next_match.date
			).order_by(desc(Draft.date)).all():
				picks = [pick.card for pick in Pick.query.filter_by(
					uid=current_user.uid, 
					draft_id=draft.draft_id
				)]
				picks = list(modo.clean_card_set(set(picks), multifaced))
				pick_perc = threshold_met(pick_list=picks, played_list=(nb_lands + spells))
				
				if pick_perc == 100:
					draft_ids_100.append(draft.draft_id)
				elif pick_perc >= 80:
					draft_ids_80.append(draft.draft_id)
				else:
					draft_ids_all.append(draft.draft_id)
			debug_log(f"draft_ids_100: {len(draft_ids_100)}")
			debug_log(f"draft_ids_80: {len(draft_ids_80)}")
			debug_log(f"draft_ids_all: {len(draft_ids_all)}")
			
			# Prioritize better matches
			possible_draft_ids = []
			if len(draft_ids_100) > 0:
				possible_draft_ids = draft_ids_100
			elif len(draft_ids_80) > 0:
				possible_draft_ids = draft_ids_80

			if len(possible_draft_ids) > 0:
				# Found next match with possible associations
				next_match_data = next_match.as_dict()
				next_match_data.update({
					'lands': sorted(list(set(lands))),
					'spells': sorted(list(set(spells))),
					'possible_draft_ids': possible_draft_ids
				})
				
				return jsonify({
					'hasNextMatch': True,
					'nextMatch': next_match_data
				})

			# Try next match in sequence - continue from where we left off
			current_match_found = False
			temp_next_match = None
			for match in remaining_matches.all():
				if match.match_id == next_match.match_id:
					current_match_found = True
					continue
				if current_match_found:
					temp_next_match = match
					break
			next_match = temp_next_match
		
		# No more matches found
		return jsonify({'hasNextMatch': False})
		
	except Exception as e:
		debug_log(f"Error in api_draft_id_update: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/input_options')
@login_required
def input_options():
	ensure_data_loaded()
	return options

@views.route('/export')
@login_required
def export():
	acquired_export_lock = False
	with export_locks_guard:
		if current_user.uid in active_export_users:
			flash('An export is already in progress for your account. Please wait for it to finish.', 'warning')
			return redirect(url_for('views.profile'))
		active_export_users.add(current_user.uid)
		acquired_export_lock = True

	try:
		file_name = f'{current_user.email}_Tables.zip'
		empty_tables = []
		export_cnt = 0
		zip_buffer = io.BytesIO()
		
		# Debug info
		debug_log(f"Export started for user: {current_user.uid}, {current_user.username}")
		
		def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
			buffer = io.BytesIO()
			with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
				df.to_excel(writer, index=False)
			buffer.seek(0)
			return buffer.getvalue()
		
		with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
			# Matches
			try:
				query = select(Match).where(
					(Match.uid == current_user.uid) & 
					(Match.p1 == current_user.username)
				)
				matches_df = pd.read_sql(query, db.engine)
				debug_log(f"Matches query returned {len(matches_df)} rows")
				
				if not matches_df.empty:
					matches_df = matches_df.drop('uid', axis=1)
					zipf.writestr(
						f'{current_user.email}_Matches.xlsx',
						dataframe_to_excel_bytes(matches_df)
					)
					export_cnt += 1
				else:
					empty_tables.append('Matches')
			except Exception as e:
				debug_log(f"Matches export error: {e}")
				empty_tables.append('Matches')
			
			# Games
			try:
				query = select(Game).where(
					(Game.uid == current_user.uid) & 
					(Game.p1 == current_user.username)
				)
				games_df = pd.read_sql(query, db.engine)
				debug_log(f"Games query returned {len(games_df)} rows")
				
				if not games_df.empty:
					games_df = games_df.drop('uid', axis=1)
					zipf.writestr(
						f'{current_user.email}_Games.xlsx',
						dataframe_to_excel_bytes(games_df)
					)
					export_cnt += 1
				else:
					empty_tables.append('Games')
			except Exception as e:
				debug_log(f"Games export error: {e}")
				empty_tables.append('Games')
			
			# Plays
			try:
				query = select(Play).where(Play.uid == current_user.uid)
				plays_df = pd.read_sql(query, db.engine)
				debug_log(f"Plays query returned {len(plays_df)} rows")
				
				if not plays_df.empty:
					plays_df = plays_df.drop('uid', axis=1)
					zipf.writestr(
						f'{current_user.email}_Plays.xlsx',
						dataframe_to_excel_bytes(plays_df)
					)
					export_cnt += 1
				else:
					empty_tables.append('Plays')
			except Exception as e:
				debug_log(f"Plays export error: {e}")
				empty_tables.append('Plays')
			
			# Picks
			try:
				query = select(Pick).where(Pick.uid == current_user.uid)
				picks_df = pd.read_sql(query, db.engine)
				debug_log(f"Picks query returned {len(picks_df)} rows")
				
				if not picks_df.empty:
					picks_df = picks_df.drop('uid', axis=1)
					zipf.writestr(
						f'{current_user.email}_Picks.xlsx',
						dataframe_to_excel_bytes(picks_df)
					)
					export_cnt += 1
				else:
					empty_tables.append('Picks')
			except Exception as e:
				debug_log(f"Picks export error: {e}")
				empty_tables.append('Picks')
			
			# Drafts
			try:
				query = select(Draft).where(Draft.uid == current_user.uid)
				drafts_df = pd.read_sql(query, db.engine)
				debug_log(f"Drafts query returned {len(drafts_df)} rows")
				
				if not drafts_df.empty:
					drafts_df = drafts_df.drop('uid', axis=1)
					zipf.writestr(
						f'{current_user.email}_Drafts.xlsx',
						dataframe_to_excel_bytes(drafts_df)
					)
					export_cnt += 1
				else:
					empty_tables.append('Drafts')
			except Exception as e:
				debug_log(f"Drafts export error: {e}")
				empty_tables.append('Drafts')
		
		# Check if any files were created
		if export_cnt == 0:
			debug_log("No data available for export - all tables empty")
			return redirect(url_for('views.index'))

		zip_buffer.seek(0)
		debug_log(f"Export successful - created {export_cnt} files")

		return send_file(
			zip_buffer,
			as_attachment=True,
			download_name=file_name,
			mimetype='application/zip'
		)
		
	except Exception as e:
		debug_log(f"Export error: {e}")
		flash(f'Export failed: {str(e)}', 'error')
		return redirect(url_for('views.index'))
	finally:
		if acquired_export_lock:
			with export_locks_guard:
				active_export_users.discard(current_user.uid)

@views.route('/best_guess', methods=['POST'])
@login_required
def best_guess():
	# Ensure data is loaded before using global variables
	ensure_data_loaded()
	
	bg_type = request.form.get('BG_Match_Set').strip()
	replace_type = request.form.get('BG_Replace').strip()
	con_count = 0
	lim_count = 0
	all_matches = Match.query.filter_by(uid=current_user.uid)
	debug_log(f"BG_Match_Set: {bg_type}")
	debug_log(f"BG_Replace: {replace_type}")
	if replace_type == 'Overwrite All':
		if (bg_type == 'Limited Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Limited Formats']) )
			for match in matches:
				cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				match.p1_subarch = modo.get_limited_subarch(cards1)
				match.p2_subarch = modo.get_limited_subarch(cards2)
				match.p1_arch = 'Limited'
				match.p2_arch = 'Limited'
				lim_count += 1
		if (bg_type == 'Constructed Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Constructed Formats']) )
			for match in matches:
				yyyy_mm = match.date[0:4] + "-" + match.date[5:7]
				cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																			 match_id=match.match_id, 
																			 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
				p1_data = modo.closest_list(set(cards1),all_decks,yyyy_mm)
				p2_data = modo.closest_list(set(cards2),all_decks,yyyy_mm)
				match.p1_subarch = p1_data[0]
				match.p2_subarch = p2_data[0]
				con_count += 1

	if replace_type == 'Replace NA':
		all_matches = all_matches.filter( (Match.p1_subarch.in_(['Unknown', 'NA'])) | (Match.p2_subarch.in_(['Unknown', 'NA'])) )
		debug_log(f"All matches: {all_matches.count()}")
		if (bg_type == 'Limited Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Limited Formats']) )
			debug_log(f"Matches1: {matches.count()}")
			for match in matches:
				if match.p1_subarch in ['Unknown', 'NA']:
					cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					match.p1_subarch = modo.get_limited_subarch(cards1)
					match.p1_arch = 'Limited'
					lim_count += 1
				if match.p2_subarch in ['Unknown', 'NA']:
					cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					match.p2_subarch = modo.get_limited_subarch(cards2)
					match.p2_arch = 'Limited'
					lim_count += 1
		if (bg_type == 'Constructed Only') or (bg_type == 'All Matches'):
			matches = all_matches.filter( Match.format.in_(options['Constructed Formats']) )
			debug_log(f"Matches2: {matches.count()}")
			for match in matches:
				yyyy_mm = match.date[0:4] + "-" + match.date[5:7]
				if match.p1_subarch in ['Unknown', 'NA']:
					cards1 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p1).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					p1_data = modo.closest_list(set(cards1),all_decks,yyyy_mm)
					match.p1_subarch = p1_data[0]
					con_count += 1
				if match.p2_subarch in ['Unknown', 'NA']:
					cards2 = [play.primary_card for play in Play.query.filter_by(uid=current_user.uid, 
																				 match_id=match.match_id, 
																				 casting_player=match.p2).filter( Play.action.in_(['Land Drop', 'Casts']) )]
					p2_data = modo.closest_list(set(cards2),all_decks,yyyy_mm)
					match.p2_subarch = p2_data[0]
					con_count += 1
	try:
		db.session.commit()
	except:
		db.session.rollback()
	return_str = 'Revised deck names for ' + str(con_count) + ' Constructed  Match'
	if con_count != 1:
		return_str += 'es'
	return_str += ' and ' + str(lim_count) + ' Limited Match'
	if lim_count != 1:
		return_str += 'es'
	return_str += '.'
	flash(return_str, category='success')
	return redirect(url_for('views.table', table_name='matches', page_num=1))

@views.route('/profile')
@login_required
def profile():
	profile_images_dir = os.path.join(current_app.root_path, 'static', 'images', 'profile')
	allowed_profile_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
	try:
		profile_images = sorted(
			[
				name for name in os.listdir(profile_images_dir)
				if os.path.isfile(os.path.join(profile_images_dir, name))
				and os.path.splitext(name.lower())[1] in allowed_profile_ext
			]
		)
	except Exception:
		profile_images = []
	if not profile_images:
		profile_images = [DEFAULT_PROFILE_IMAGE]
	selected_profile_image = current_user.profile_image if getattr(current_user, 'profile_image', None) in profile_images else profile_images[0]

	def get_max_streak(table,streak_type):
		max_streak = 0
		max_streak_start_date = ''
		max_streak_end_date = 'Current'
		streak = 0
		streak_start_date = ''
		for i in table:
			if (i.match_winner == 'P1') and (streak_type == 'win'):
				streak += 1
			elif (i.match_winner == 'P2') and (streak_type == 'lose'):
				streak += 1
			else:
				if streak == max_streak:
					max_streak_end_date = i.date
				streak = 0
			if streak == 1:
				streak_start_date = i.date
			if streak >= max_streak:
				max_streak = streak
				max_streak_start_date = streak_start_date
				max_streak_end_date = 'Current'
		if max_streak_end_date == 'Current':
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[8:10]}/{max_streak_start_date[0:4]}', max_streak_end_date]
		else:
			return [max_streak, f'{max_streak_start_date[5:7]}/{max_streak_start_date[8:10]}/{max_streak_start_date[0:4]}', f'{max_streak_end_date[5:7]}/{max_streak_end_date[8:10]}/{max_streak_end_date[0:4]}']
	def get_best_format(table):
		formats = {}
		max_format = 'None'
		max_perc = '0.0%'
		max_float = 0.0
		max_games = 0
		for i in table:
			#debug_log(i)
			if i[0] not in formats.keys():
				formats[i[0]] = [0,0]
			if i[1] == 'P1':
				formats[i[0]][0] = i[2]
			elif i[1] == 'P2':
				formats[i[0]][1] = i[2]
		for i in formats:
			if formats[i][0] == 0:
				formats[i].append(0)
				formats[i].append('0.0%')
			else:
				formats[i].append( formats[i][0]/(formats[i][0]+formats[i][1]) )
				formats[i].append( str(round((formats[i][0]/(formats[i][0]+formats[i][1]))*100,1))+'%' )
				if (formats[i][2] > max_float) and ((formats[i][0] + formats[i][1]) >= 25):
					max_format = i
					max_perc = formats[i][3]
					max_float = formats[i][2]
					max_games = formats[i][0] + formats[i][1]
		return [max_format, max_perc, max_float, max_games]

	table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(Match.date).all()
	fave_format = db.session.query(Match.format, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.format).order_by(desc(func.count(Match.uid))).first()
	fave_deck = db.session.query(Match.p1_subarch, Match.format, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.p1_subarch, Match.format).order_by(desc(func.count(Match.uid))).first()
	best_format = db.session.query(Match.format, Match.match_winner, func.count(Match.uid)).filter(Match.uid == current_user.uid, Match.p1 == current_user.username).group_by(Match.format, Match.match_winner).all()
	
	longest = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username)
	longest = longest.join(Game, (Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)).add_entity(Game)

	longest_game = longest.order_by(desc(Game.turns), desc(Match.date)).first()

	stats_dict = {}
	stats_dict['matches_played'] = len(table)
	try:
		stats_dict['fave_format'] = list(fave_format)
	except TypeError:
		stats_dict['fave_format'] = ['None', 0]
	try:
		stats_dict['fave_deck'] = list(fave_deck)
	except TypeError:
		stats_dict['fave_deck'] = ['None', 'NA', 0]
	stats_dict['max_win_streak'] = get_max_streak(table=table,streak_type='win')
	stats_dict['max_lose_streak'] = get_max_streak(table=table,streak_type='lose')
	stats_dict['best_format'] = get_best_format(table=best_format)
	if longest_game:
		stats_dict['longest_game'] = [longest_game[1].turns, longest_game[0].date[5:7]+'/'+longest_game[0].date[8:10]+'/'+longest_game[0].date[0:4], longest_game[0].p1_subarch, longest_game[0].p2_subarch]
	else:
		stats_dict['longest_game'] = [0, 'NA', 'NA', 'NA']

	# Generate match history data for profile page
	def match_result(p1_wins, p2_wins):
		if p1_wins == p2_wins:
			return f'NA {p1_wins}-{p2_wins}'
		elif p1_wins > p2_wins:
			return f'Win {p1_wins}-{p2_wins}'
		elif p2_wins > p1_wins:
			return f'Loss {p1_wins}-{p2_wins}'
	
	def format_match_format(fmt, limited_format='NA'):
		fmt_norm = (fmt or 'NA').strip() if isinstance(fmt, str) else str(fmt or 'NA')
		lfmt_norm = (limited_format or '').strip() if isinstance(limited_format, str) else str(limited_format or '').strip()
		if lfmt_norm and lfmt_norm.upper() != 'NA':
			return f'{fmt_norm} - {lfmt_norm}'
		return fmt_norm

	def format_date(date_str):
		"""Format date string to 'Month Day, Year' format"""
		if not date_str:
			return str(date_str)

		try:
			date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d-%H:%M').date()
			# Format as "July 6, 2025" (cross-platform compatible)
			formatted_date = date_obj.strftime('%B %d, %Y')
			# Remove leading zero from day if present (e.g., "July 06" -> "July 6")
			return formatted_date.replace(' 0', ' ')
		except ValueError:
			return date_str

	# Get recent match history (last 10 matches) with optional draft info
	match_history_query = (
		Match.query
		.filter(Match.uid == current_user.uid, Match.p1 == current_user.username)
		.outerjoin(Draft, (Draft.uid == Match.uid) & (Draft.draft_id == Match.draft_id))
		.add_entity(Draft)
		.order_by(desc(Match.date))
		.limit(10)
	)
	
	match_history_data = match_history_query.all()
	match_history_list = []
	
	# Build recent matches list, showing draft format when applicable
	for match, draft in match_history_data:
		match_dict = {
			'Date': format_date(match.date),
			'Opponent': match.p2,
			'Deck': match.p1_subarch,
			'Opp_Deck': match.p2_subarch,
			'Match_Result': match_result(match.p1_wins, match.p2_wins),
			'Match_Format': format_match_format(match.format, match.limited_format)
		}
		match_history_list.append(match_dict)

	return render_template('profile.html', user=current_user, stats=stats_dict, match_history=match_history_list, profile_images=profile_images, selected_profile_image=selected_profile_image)

@views.route('/edit_profile', methods=['POST'])
@login_required
def edit_profile():
	#new_email = request.get_json()['ProfileEmailInputText']
	#new_name = request.get_json()['ProfileNameInputText']
	payload = request.get_json() or {}
	new_username = (payload.get('ProfileUsernameInputText') or '').strip()
	new_profile_image = (payload.get('ProfileImageInputValue') or '').strip()

	profile_images_dir = os.path.join(current_app.root_path, 'static', 'images', 'profile')
	allowed_profile_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
	try:
		available_profile_images = {
			name for name in os.listdir(profile_images_dir)
			if os.path.isfile(os.path.join(profile_images_dir, name))
			and os.path.splitext(name.lower())[1] in allowed_profile_ext
		}
	except Exception:
		available_profile_images = {DEFAULT_PROFILE_IMAGE}
	if not available_profile_images:
		available_profile_images = {DEFAULT_PROFILE_IMAGE}
	if new_profile_image not in available_profile_images:
		new_profile_image = DEFAULT_PROFILE_IMAGE

	user = Player.query.filter_by(uid=current_user.uid).first()
	current_username = user.username or ''
	current_profile_image = user.profile_image or DEFAULT_PROFILE_IMAGE
	next_username = new_username if new_username else current_username
	next_profile_image = new_profile_image if new_profile_image else DEFAULT_PROFILE_IMAGE

	if (next_username == current_username) and (next_profile_image == current_profile_image):
		return jsonify({'success': True, 'username': current_username, 'profile_image': current_profile_image, 'updated': False})

	user.username = next_username
	user.profile_image = next_profile_image
	try:
		db.session.commit()
	except:
		db.session.rollback()
		return jsonify({'success': False, 'error': 'Failed to update profile'}), 500
	
	return jsonify({'success': True, 'username': user.username, 'profile_image': user.profile_image, 'updated': True})

@views.route('/filter_options', methods=['GET'])
@login_required
def filter_options():
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return 'Forbidden', 403
	filter_options_dict = {'Date1':'2000-01-01','Date2':'2999-12-31'}

	table = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
	plays_table = Play.query.filter_by(uid=current_user.uid, casting_player=current_user.username)

	if (table.count() == 0) or (plays_table.count() == 0):
		return filter_options_dict

	filter_options_dict['Card'] = [i.primary_card for i in plays_table.with_entities(Play.primary_card).distinct().order_by(Play.primary_card).all()]
	filter_options_dict['Card'].remove('NA')
	filter_options_dict['Opponent'] = [i.p2 for i in table.with_entities(Match.p2).distinct().order_by(Match.p2).all()]
	filter_options_dict['Opponent'].sort(key=str.lower)
	filter_options_dict['Format'] = [i.format for i in table.with_entities(Match.format).distinct().order_by(Match.format).all()]
	filter_options_dict['Deck'] = [i.p1_subarch for i in table.with_entities(Match.p1_subarch).distinct().order_by(Match.p1_subarch).all()]
	filter_options_dict['Opp. Deck'] = [i.p2_subarch for i in table.with_entities(Match.p2_subarch).distinct().order_by(Match.p2_subarch).all()]
	filter_options_dict['Action'] = ['Land Drop','Casts','Activated Ability','Triggers']
	date1 = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username).order_by(Match.date.asc()).first().date[0:10].replace('-','')
	filter_options_dict['Date1'] = date1[0:4] + '-' + date1[4:6] + '-' + date1[6:]
	date2 = Match.query.filter(Match.uid == current_user.uid, Match.p1 == current_user.username).order_by(desc(Match.date)).first().date[0:10].replace('-','')
	filter_options_dict['Date2'] = date2[0:4] + '-' + date2[4:6] + '-' + date2[6:]
	return filter_options_dict

@views.route('/getting_started', methods=['GET'])
def getting_started():
	return render_template('gettingstarted.html', user=current_user)

@views.route('/faq', methods=['GET'])
def faq():
	return render_template('faq.html', user=current_user)

@views.route('/changelog', methods=['GET'])
def changelog():
	return render_template('changelog.html', user=current_user)

@views.route('/zip', methods=['GET'])
def zip():
	return send_file(os.path.join(os.getcwd() + '\\website\\static', 'Zip-MTGO-Logs.exe'), as_attachment=True)

@views.route('/reprocess', methods=['POST'])
@login_required
def reprocess():
	task = reprocess_logs.delay({'email':current_user.email, 'user_id':current_user.uid, 'username':current_user.username})

	flash(f'Your data is now being re-processed. This may take several minutes depending on the number of files. A Load Report will be emailed upon completion.', category='success')
	return redirect('/')

@views.route('/data_dictionary', methods=['GET'])
def data_dict():
  return render_template('datadict.html', user=current_user)

@views.route('/dashboards', methods=['GET'])
@login_required
def dashboards():
	return render_template('dashboards.html', user=current_user)

@views.route('/api/dashboard/filtered-options', methods=['POST'])
@login_required
def api_dashboard_filtered_options():
	"""Get filtered dropdown options based on current filter selections"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get current filter values
		data = request.get_json()
		current_filters = data.get('filters', {})
		
		# Start with base query for user's matches
		base_query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
		
		# Apply current filters EXCEPT card filter (to avoid complex joins for cascading)
		filters_without_card = current_filters.copy()
		card_filter = filters_without_card.pop('card', None)
		
		# Apply non-card filters first
		filtered_matches_query = apply_dashboard_filters(base_query, filters_without_card)
		filtered_matches = filtered_matches_query.all()
		match_ids = [m.match_id for m in filtered_matches]
		
		# If card filter is specified, further filter the matches
		if card_filter and match_ids:
			# Get matches that contain the specified card
			card_match_ids = Play.query.filter(
				Play.uid == current_user.uid,
				Play.casting_player == current_user.username,
				Play.primary_card == card_filter,
				Play.match_id.in_(match_ids)
			).with_entities(Play.match_id).distinct().all()
			
			card_match_ids = [m.match_id for m in card_match_ids]
			filtered_matches = [m for m in filtered_matches if m.match_id in card_match_ids]
			match_ids = card_match_ids
		
		# Get plays data for card filtering options
		plays_query = Play.query.filter(
			Play.uid == current_user.uid,
			Play.casting_player == current_user.username,
			Play.primary_card != 'NA'
		)
		if match_ids:
			plays_query = plays_query.filter(Play.match_id.in_(match_ids))
		plays = plays_query.all()
		
		# Build filtered options
		filtered_options = {}
		
		# Cards (from plays in filtered matches)
		card_options = list(set([play.primary_card for play in plays]))
		card_options.sort()
		filtered_options['Card'] = card_options
		
		# Opponents
		opponent_options = list(set([m.p2 for m in filtered_matches if m.p2]))
		opponent_options.sort(key=str.lower)
		filtered_options['Opponent'] = opponent_options
		
		# Formats
		format_options = list(set([m.format for m in filtered_matches if m.format]))
		format_options.sort()
		filtered_options['Format'] = format_options
			
		# Decks (p1_subarch)
		deck_options = list(set([m.p1_subarch for m in filtered_matches if m.p1_subarch]))
		deck_options.sort()
		filtered_options['Deck'] = deck_options
		
		# Opponent Decks (p2_subarch)
		opp_deck_options = list(set([m.p2_subarch for m in filtered_matches if m.p2_subarch]))
		opp_deck_options.sort()
		filtered_options['Opp. Deck'] = opp_deck_options
		
		# Date range (from filtered matches)
		if filtered_matches:
			dates = [m.date for m in filtered_matches if m.date]
			if dates:
				dates.sort()
				filtered_options['Date1'] = dates[0][:10]
				filtered_options['Date2'] = dates[-1][:10]
			else:
				filtered_options['Date1'] = '2000-01-01'
				filtered_options['Date2'] = '2999-12-31'
		else:
			filtered_options['Date1'] = '2000-01-01'
			filtered_options['Date2'] = '2999-12-31'
		
		return jsonify(filtered_options)
		
	except Exception as e:
		debug_log(f"Error in api_dashboard_filtered_options: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/dashboard/generate', methods=['POST'])
@login_required
def api_dashboard_generate():
	"""Generate dashboard data based on type and filters"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get request data
		data = request.get_json()
		dashboard_type = data.get('dashboard_type')
		filters = data.get('filters', {})
		
		if not dashboard_type:
			return jsonify({'error': 'Dashboard type is required'}), 400
		
		# Apply base filters to get user's matches
		base_query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username)
		
		# Apply filters
		filtered_query = apply_dashboard_filters(base_query, filters)
		
		# Generate dashboard data based on type
		dashboard_data = {}
		
		if dashboard_type == 'match-performance':
			dashboard_data = generate_match_performance_dashboard(filtered_query, filters)
		elif dashboard_type == 'card-analysis':
			dashboard_data = generate_card_analysis_dashboard(filtered_query, filters)
		elif dashboard_type == 'opponent-analysis':
			dashboard_data = generate_opponent_analysis_dashboard(filtered_query, filters)
		elif dashboard_type == 'game-data':
			dashboard_data = generate_game_data_dashboard(filtered_query, filters)
		else:
			return jsonify({'error': 'Invalid dashboard type'}), 400
		
		return jsonify({
			'success': True,
			'dashboard_type': dashboard_type,
			'filters_applied': filters,
			'data': dashboard_data
		})
		
	except Exception as e:
		debug_log(f"Error in api_dashboard_generate: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

def apply_dashboard_filters(query, filters):
	"""Apply filters to the match query"""
	try:
		# Filter by opponent
		if filters.get('opponent'):
			query = query.filter(Match.p2 == filters['opponent'])
		
		# Filter by format
		if filters.get('format'):
			query = query.filter(Match.format == filters['format'])
		
		# Filter by deck (p1_subarch)
		if filters.get('deck'):
			query = query.filter(Match.p1_subarch == filters['deck'])
		
		# Filter by opponent deck (p2_subarch)
		if filters.get('oppDeck'):
			query = query.filter(Match.p2_subarch == filters['oppDeck'])
		
		# Filter by date range
		if filters.get('startDate'):
			query = query.filter(Match.date >= filters['startDate'])
		if filters.get('endDate'):
			query = query.filter(Match.date <= filters['endDate'] + '-23:59')
		
		# Filter by card (requires joining with Play table)
		if filters.get('card'):
			query = query.join(Game, (Match.match_id == Game.match_id) & (Match.uid == Game.uid))\
						 .join(Play, (Game.match_id == Play.match_id) & (Game.game_num == Play.game_num) & (Game.uid == Play.uid))\
						 .filter(Play.primary_card == filters['card'])\
						 .filter(Play.casting_player == current_user.username)
		
		return query
		
	except Exception as e:
		debug_log(f"Error applying dashboard filters: {str(e)}")
		raise e

def apply_dashboard_filters_to_play_query(query, filters):
	"""Apply filters to a Play query that's already joined with Match table"""
	try:
		# Filter by opponent
		if filters.get('opponent'):
			query = query.filter(Match.p2 == filters['opponent'])
		
		# Filter by format
		if filters.get('format'):
			query = query.filter(Match.format == filters['format'])
		
		# Filter by deck (p1_subarch)
		if filters.get('deck'):
			query = query.filter(Match.p1_subarch == filters['deck'])
		
		# Filter by opponent deck (p2_subarch)
		if filters.get('oppDeck'):
			query = query.filter(Match.p2_subarch == filters['oppDeck'])
		
		# Filter by date range
		if filters.get('startDate'):
			query = query.filter(Match.date >= filters['startDate'])
		if filters.get('endDate'):
			query = query.filter(Match.date <= filters['endDate'] + '-23:59')
		
		# Filter by card (since we're already querying Play table)
		if filters.get('card'):
			query = query.filter(Play.primary_card == filters['card'])
		
		return query
		
	except Exception as e:
		debug_log(f"Error applying dashboard filters to Play query: {str(e)}")
		raise e

def apply_dashboard_filters_to_game_query(query, filters):
	"""Apply filters to a Game query that's already joined with Match table"""
	try:
		# Filter by opponent
		if filters.get('opponent'):
			query = query.filter(Match.p2 == filters['opponent'])
		
		# Filter by format
		if filters.get('format'):
			query = query.filter(Match.format == filters['format'])
		
		# Filter by deck (p1_subarch)
		if filters.get('deck'):
			query = query.filter(Match.p1_subarch == filters['deck'])
		
		# Filter by opponent deck (p2_subarch)
		if filters.get('oppDeck'):
			query = query.filter(Match.p2_subarch == filters['oppDeck'])
		
		# Filter by date range
		if filters.get('startDate'):
			query = query.filter(Match.date >= filters['startDate'])
		if filters.get('endDate'):
			query = query.filter(Match.date <= filters['endDate'] + '-23:59')
		
		# Filter by card (requires additional join with Play table)
		if filters.get('card'):
			query = query.join(Play, (Game.match_id == Play.match_id) & (Game.game_num == Play.game_num) & (Game.uid == Play.uid))\
						 .filter(Play.primary_card == filters['card'])
		
		return query
		
	except Exception as e:
		debug_log(f"Error applying dashboard filters to Game query: {str(e)}")
		raise e

def generate_match_performance_dashboard(filtered_query, filters):
	"""Generate match performance dashboard data"""
	try:
		matches = filtered_query.all()
			
		# Calculate metrics
		total_matches = len(matches)
		wins = len([m for m in matches if m.match_winner == 'P1'])
		die_roll_wins = len([m for m in matches if m.roll_winner == 'P1'])
		losses = total_matches - wins
		win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
		die_roll_wr = (die_roll_wins / total_matches * 100) if total_matches > 0 else 0
		
		# Calculate games statistics
		total_games = sum([m.p1_wins + m.p2_wins for m in matches])
		avg_games_per_match = (total_games / total_matches) if total_matches > 0 else 0

		# Build rolling match win rate (last 25 matches)
		# Use already-filtered matches; order by date
		matches_seq = sorted(matches, key=lambda m: (m.date or ''))
		# Convert to sequential outcomes (1 for match win, 0 otherwise)
		match_outcomes = [1 if m.match_winner == 'P1' else 0 for m in matches_seq]
		labels_matches = list(range(1, len(match_outcomes) + 1))
		window = 25
		rolling_wr = []
		cumulative_wr = []
		cumsum = 0
		from collections import deque
		window_q = deque()
		cum_total = 0
		count_so_far = 0
		for val in match_outcomes:
			window_q.append(val)
			cumsum += val
			if len(window_q) > window:
				cumsum -= window_q.popleft()
			current_len = len(window_q)
			rolling_wr.append(round((cumsum / current_len) * 100, 1) if current_len > 0 else 0)
			# cumulative average up to this match index
			count_so_far += 1
			cum_total += val
			cumulative_wr.append(round((cum_total / count_so_far) * 100, 1))

		rolling_win_chart = {
			'title': 'Rolling Match Win Rate',
			'type': 'line',
			'xTitle': 'Match Number',
			'yTitle': 'Win Rate %',
			'chartTitle': 'Rolling Match Win Rate',
			'chartSubtitle': 'Previous 25 Matches',
			'data': {
				'labels': labels_matches,
				'datasets': [
					{
						'label': 'Win Rate % (Last 25)',
						'data': rolling_wr,
						'borderColor': '#0039A6',
						'backgroundColor': 'rgba(0,57,166,0.15)',
						'tension': 0.25,
						'fill': False,
						'borderWidth': 2
					},
					{
						'label': 'Win Rate % (Overall)',
						'data': cumulative_wr,
						'borderColor': '#9ca3af',
						'backgroundColor': 'transparent',
						'tension': 0.25,
						'fill': False,
						'borderWidth': 2
					}
				]
			}
		}
		
		# Performance by Format
		if matches:
			df = pd.DataFrame([{
				'format': m.format,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by format and calculate stats
			format_stats = df.groupby('format').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			format_stats.columns = ['total_matches', 'wins']
			format_stats['losses'] = format_stats['total_matches'] - format_stats['wins']
			format_stats['win_pct'] = (format_stats['wins'] / format_stats['total_matches'] * 100).round(1)
			format_stats = format_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get format as a column
			format_stats = format_stats.reset_index()
			
			# Create table data for the return JSON
			format_performance_table = {
				'title': 'Performance by Format',
				'headers': ['<center>Format</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['format'],
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in format_stats.iterrows()],
				'columnWidths': ['25%', '25%', '25%', '25%']
			}
		else:
			format_performance_table = {
				'title': 'Performance by Format',
				'headers': ['<center>Format</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [],
				'columnWidths': ['25%', '25%', '25%', '25%']
			}
		
		# Performance by Match Type
		if matches:
			df = pd.DataFrame([{
				'match_type': m.match_type,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by format and calculate stats
			matchtype_stats = df.groupby('match_type').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			matchtype_stats.columns = ['total_matches', 'wins']
			matchtype_stats['losses'] = matchtype_stats['total_matches'] - matchtype_stats['wins']
			matchtype_stats['win_pct'] = (matchtype_stats['wins'] / matchtype_stats['total_matches'] * 100).round(1)
			matchtype_stats = matchtype_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get format as a column
			matchtype_stats = matchtype_stats.reset_index()
			
			# Create table data for the return JSON
			matchtype_performance_table = {
				'title': 'Performance by Match Type',
				'headers': ['<center>Match Type</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['match_type'],
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in matchtype_stats.iterrows()],
				'columnWidths': ['25%', '25%', '25%', '25%']
			}
		else:
			matchtype_performance_table = {
				'title': 'Performance by Match Type',
				'headers': ['<center>Match Type</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [],
				'columnWidths': ['25%', '25%', '25%', '25%']
			}

		# Decks Played
		if matches:
			df = pd.DataFrame([{
				'p1_subarch': m.p1_subarch,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by p1_subarch and calculate stats
			deck_stats = df.groupby('p1_subarch').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			deck_stats.columns = ['total_matches', 'wins']
			deck_stats['losses'] = deck_stats['total_matches'] - deck_stats['wins']
			deck_stats['win_pct'] = (deck_stats['wins'] / deck_stats['total_matches'] * 100).round(1)
			deck_stats['share_pct'] = (deck_stats['total_matches'] / total_matches * 100).round(1)
			deck_stats = deck_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get p1_subarch as a column
			deck_stats = deck_stats.reset_index()
			
			# Create table data for the return JSON
			deck_performance_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['p1_subarch'],
					f"<center>{row['wins'] + row['losses']} - ({row['share_pct']:.1f}%)</center>",
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in deck_stats.iterrows()],
				'columnWidths': ['20%', '20%', '20%', '20%', '20%']
			}
		else:
			deck_performance_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [],
				'columnWidths': ['20%', '20%', '20%', '20%', '20%']
			}

		# Observed Metagame
		if matches:
			df = pd.DataFrame([{
				'p2_subarch': m.p2_subarch,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by p2_subarch and calculate stats
			deck_stats = df.groupby('p2_subarch').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			deck_stats.columns = ['total_matches', 'wins']
			deck_stats['losses'] = deck_stats['total_matches'] - deck_stats['wins']
			deck_stats['win_pct'] = (deck_stats['wins'] / deck_stats['total_matches'] * 100).round(1)
			deck_stats['share_pct'] = (deck_stats['total_matches'] / total_matches * 100).round(1)
			deck_stats = deck_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get p2_subarch as a column
			deck_stats = deck_stats.reset_index()
			
			# Create table data for the return JSON
			oppdeck_performance_table = {
				'title': 'Observed Metagame',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [[
					row['p2_subarch'],
					f"<center>{row['wins'] + row['losses']} - ({row['share_pct']:.1f}%)</center>",
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in deck_stats.iterrows()],
				'columnWidths': ['20%', '20%', '20%', '20%', '20%']
			}
		else:
			oppdeck_performance_table = {
				'title': 'Observed Metagame',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Match Win%</center>'],
				'height': '214px',
				'rows': [],
				'columnWidths': ['20%', '20%', '20%', '20%', '20%']
			}

		return {
			'metrics': [
				{
					'title': 'Win Rate',
					'value': f'{win_rate:.1f}%',
					'subtitle': f'{wins} wins, {losses} losses',
					'type': 'percentage'
				},
				{
					'title': 'Total Matches',
					'value': str(total_matches),
					'subtitle': 'In selected period',
					'type': 'count'
				},
				{
					'title': 'Die Roll Win Rate',
					'value': f'{die_roll_wr:.1f}%',
					'subtitle': '',
					'type': 'percentage'
				}
			],
			'charts': [rolling_win_chart],
			'table_grids': [
				{
					'type': '2x2',
					'title': 'Performance Overview',
					'grid': [
						[format_performance_table, matchtype_performance_table],
						[deck_performance_table, oppdeck_performance_table]
					]
				}
			],
			'tables': [
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating match performance dashboard: {str(e)}")
		raise e

def generate_card_analysis_dashboard(filtered_query, filters):
	"""Generate card analysis dashboard data"""
	try:
		# Get perspective from filters (default to 'hero')
		perspective = filters.get('perspective', 'hero')
		
		# Set up casting player filter based on perspective
		if perspective == 'opponents':
			casting_player_filter = Play.casting_player != current_user.username
			perspective_label = 'Opponents'
		else:
			casting_player_filter = Play.casting_player == current_user.username
			perspective_label = 'Hero'
		
		# Get plays data for filtered matches with joins
		plays_hero = db.session.query(Play).join(Match, 
			(Play.uid == Match.uid) & (Play.match_id == Match.match_id)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username,
			Play.casting_player == current_user.username,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		)
		# Apply the same filters as the filtered_query
		plays_hero = apply_dashboard_filters_to_play_query(plays_hero, filters).all()

		plays_opp = db.session.query(Play).join(Match,
			(Play.uid == Match.uid) & (Play.match_id == Match.match_id)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username,
			Play.casting_player != current_user.username,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		)
		# Apply the same filters as the filtered_query
		plays_opp = apply_dashboard_filters_to_play_query(plays_opp, filters).all()
			
		# Basic card frequency analysis
		card_frequency_hero = {}
		for play in plays_hero:
			card = play.primary_card
			card_frequency_hero[card] = card_frequency_hero.get(card, 0) + 1

		card_frequency_opp = {}
		for play in plays_opp:
			card = play.primary_card
			card_frequency_opp[card] = card_frequency_opp.get(card, 0) + 1
		
		# Sort by frequency
		top_cards_hero = sorted(card_frequency_hero.items(), key=lambda x: x[1], reverse=True)[:10]
		top_cards_opp = sorted(card_frequency_opp.items(), key=lambda x: x[1], reverse=True)[:10]
			
		# Get all games for filtered matches with joins
		games = db.session.query(Game).join(Match,
			(Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username
		)
		# Apply the same filters as the filtered_query
		games = apply_dashboard_filters_to_game_query(games, filters).all()
		
		# Helper to safely embed strings in JS onclick
		def escape_for_js(text):
			if not isinstance(text, str):
				text = str(text)
			return text.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')

		# Game 1 Analysis
		games_g1 = [g for g in games if g.game_num == 1]
		total_games_g1 = len(games_g1)
		
		# Get plays for Game 1 with joins
		plays_g1 = db.session.query(Play).join(Match,
			(Play.uid == Match.uid) & (Play.match_id == Match.match_id)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username,
			casting_player_filter,
			Play.game_num == 1,
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		)
		# Apply the same filters as the filtered_query
		plays_g1 = apply_dashboard_filters_to_play_query(plays_g1, filters).all()
		
		# Calculate Game 1 card statistics
		if plays_g1 and total_games_g1 > 0:
			df_g1 = pd.DataFrame([{
				'card': p.primary_card,
				'match_id': p.match_id,
				'game_num': p.game_num
			} for p in plays_g1])
			
			# Count unique games per card (create a composite key)
			df_g1['game_key'] = df_g1['match_id'] + '_' + df_g1['game_num'].astype(str)
			card_games_g1 = df_g1.groupby('card').agg({
				'game_key': 'nunique'
			}).reset_index()
			card_games_g1.columns = ['card', 'games_cast']
			
			# Calculate games cast percentage
			# Default denominator: total Game 1 count
			card_games_g1['games_cast_pct'] = (card_games_g1['games_cast'] / total_games_g1 * 100).round(1)
			# If a specific card is selected, adjust ONLY that card's denominator to the
			# number of unique games where that selected card was cast (for this perspective)
			selected_card_local = (filters.get('card') or '').strip()
			if selected_card_local:
				selected_game_keys = set(
					f"{p.match_id}_{p.game_num}"
					for p in plays_g1 if p.primary_card == selected_card_local
				)
				denom_g1 = len(selected_game_keys) or total_games_g1
				mask_sel = card_games_g1['card'] == selected_card_local
				if mask_sel.any():
					card_games_g1.loc[mask_sel, 'games_cast_pct'] = (
						card_games_g1.loc[mask_sel, 'games_cast'] / denom_g1 * 100
					).round(1)

			# Filter out rows below threshold
			card_games_g1 = card_games_g1[(card_games_g1['games_cast_pct'] >= 2.5)]

			# Calculate Hero Game Win% per card for Game 1 using perspective-specific games
			card_winrates_g1 = []
			for _, row in card_games_g1.iterrows():
				card = row['card']
				# Find games where this card was cast by the relevant perspective
				card_plays = [p for p in plays_g1 if p.primary_card == card]
				card_game_keys = set((p.match_id, p.game_num) for p in card_plays)
				# Find corresponding games and count hero wins
				card_games = [g for g in games_g1 if (g.match_id, g.game_num) in card_game_keys]
				wins = len([g for g in card_games if g.game_winner == 'P1'])
				total = len(card_games)
				win_rate = (wins / total * 100) if total > 0 else 0
				card_winrates_g1.append(win_rate)
			card_games_g1['game_win_pct'] = [round(x, 1) for x in card_winrates_g1]
			
			# Sort by games cast descending
			card_games_g1 = card_games_g1.sort_values('games_cast', ascending=False)
			
			game1_table = {
				'title': f'Pre-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
        'rows': [[
          f"<a href=\"#\" onclick=\"filterByCard('{escape_for_js(row['card'])}'); return false;\" style=\"color: var(--sky-blue); text-decoration: none; font-weight: 600; cursor: pointer;\" onmouseover=\"this.style.textDecoration='underline'\" onmouseout=\"this.style.textDecoration='none'\">{row['card']}</a>",
					f"<center>{int(row['games_cast'])} - ({row['games_cast_pct']:.1f}%)</center>",
					f"<center>{row['game_win_pct']:.1f}%</center>"
				] for _, row in card_games_g1.iterrows()],
				'columnWidths': ['34%', '33%', '33%']
			}
		else:
			game1_table = {
				'title': f'Pre-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': [],
				'columnWidths': ['34%', '33%', '33%']
			}
		
		# Games 2/3 Analysis
		games_g23 = [g for g in games if g.game_num in [2, 3]]
		total_games_g23 = len(games_g23)
		
		# Get plays for Games 2/3 with joins
		plays_g23 = db.session.query(Play).join(Match,
			(Play.uid == Match.uid) & (Play.match_id == Match.match_id)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username,
			casting_player_filter,
			Play.game_num.in_([2, 3]),
			Play.action == 'Casts',
			Play.primary_card != 'NA'
		)
		# Apply the same filters as the filtered_query
		plays_g23 = apply_dashboard_filters_to_play_query(plays_g23, filters).all()
		
		# Calculate Games 2/3 card statistics
		if plays_g23 and total_games_g23 > 0:
			df_g23 = pd.DataFrame([{
				'card': p.primary_card,
				'match_id': p.match_id,
				'game_num': p.game_num
			} for p in plays_g23])
			
			# Count unique games per card (create a composite key)
			df_g23['game_key'] = df_g23['match_id'] + '_' + df_g23['game_num'].astype(str)
			card_games_g23 = df_g23.groupby('card').agg({
				'game_key': 'nunique'
			}).reset_index()
			card_games_g23.columns = ['card', 'games_cast']
			
			# Calculate games cast percentage
			# Default denominator: total Games 2/3 count
			card_games_g23['games_cast_pct'] = (card_games_g23['games_cast'] / total_games_g23 * 100).round(1)
			# If a specific card is selected, adjust ONLY that card's denominator to the
			# number of unique games where that selected card was cast (for this perspective)
			selected_card_local = (filters.get('card') or '').strip()
			if selected_card_local:
				selected_game_keys_g23 = set(
					f"{p.match_id}_{p.game_num}"
					for p in plays_g23 if p.primary_card == selected_card_local
				)
				denom_g23 = len(selected_game_keys_g23) or total_games_g23
				mask_sel_g23 = card_games_g23['card'] == selected_card_local
				if mask_sel_g23.any():
					card_games_g23.loc[mask_sel_g23, 'games_cast_pct'] = (
						card_games_g23.loc[mask_sel_g23, 'games_cast'] / denom_g23 * 100
					).round(1)

			card_games_g23 = card_games_g23[(card_games_g23['games_cast_pct'] >= 2.5)]

			# Calculate Hero Game Win% per card for Games 2/3 using perspective-specific games
			card_winrates_g23 = []
			for _, row in card_games_g23.iterrows():
				card = row['card']
				# Find games where this card was cast by the relevant perspective
				card_plays = [p for p in plays_g23 if p.primary_card == card]
				card_game_keys = set((p.match_id, p.game_num) for p in card_plays)
				# Find corresponding games and count hero wins
				card_games = [g for g in games_g23 if (g.match_id, g.game_num) in card_game_keys]
				wins = len([g for g in card_games if g.game_winner == 'P1'])
				total = len(card_games)
				win_rate = (wins / total * 100) if total > 0 else 0
				card_winrates_g23.append(win_rate)
			card_games_g23['game_win_pct'] = [round(x, 1) for x in card_winrates_g23]
			
			# Sort by games cast descending
			card_games_g23 = card_games_g23.sort_values('games_cast', ascending=False)
			
			games23_table = {
				'title': f'Post-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
        'rows': [[
          f"<a href=\"#\" onclick=\"filterByCard('{escape_for_js(row['card'])}'); return false;\" style=\"color: var(--sky-blue); text-decoration: none; font-weight: 600; cursor: pointer;\" onmouseover=\"this.style.textDecoration='underline'\" onmouseout=\"this.style.textDecoration='none'\">{row['card']}</a>",
					f"<center>{int(row['games_cast'])} - ({row['games_cast_pct']:.1f}%)</center>",
					f"<center>{row['game_win_pct']:.1f}%</center>"
				] for _, row in card_games_g23.iterrows()],
				'columnWidths': ['34%', '33%', '33%']
			}
		else:
			games23_table = {
				'title': f'Post-Sideboard Card Performance ({perspective_label})',
				'headers': ['<center>Card</center>', '<center>Games Cast</center>', '<center>Hero Game Win%</center>'],
				'height': '400px',
				'rows': [],
				'columnWidths': ['34%', '33%', '33%']
			}

		# If both Pre- and Post-SB tables are small (<=5 rows), reduce height by 50%
		try:
			g1_rows = len(game1_table.get('rows', []))
			g23_rows = len(games23_table.get('rows', []))
			if g1_rows <= 1 and g23_rows <= 1:
				game1_table['height'] = '100px'
				games23_table['height'] = '100px'
			elif g1_rows <= 5 and g23_rows <= 5:
				game1_table['height'] = '200px'
				games23_table['height'] = '200px'
		except Exception:
			pass

		# Build dual-axis win rate by turn chart for selected card (if any)
		selected_card = (filters.get('card') or '').strip()
		winrate_chart = None
		if selected_card:
			play_turns_query = db.session.query(
				Play.turn_num.label('turn_num'),
				Game.game_winner.label('game_winner'),
				Play.match_id.label('match_id'),
				Play.game_num.label('game_num')
			).join(
				Game, (Play.uid == Game.uid) & (Play.match_id == Game.match_id) & (Play.game_num == Game.game_num)
			).join(
				Match, (Match.uid == Game.uid) & (Match.match_id == Game.match_id) & (Match.p1 == Game.p1)
			).filter(
				Match.uid == current_user.uid,
				Match.p1 == current_user.username,
				Play.action == 'Casts',
				Play.primary_card != 'NA',
				casting_player_filter
			)
			play_turns_query = apply_dashboard_filters_to_play_query(play_turns_query, filters)
			rows = play_turns_query.all()
			from collections import defaultdict
			turn_to_games = defaultdict(set)
			turn_to_wins = defaultdict(set)
			for r in rows:
				if r.turn_num is None:
					continue
				key = (r.match_id, r.game_num)
				turn_to_games[r.turn_num].add(key)
				if r.game_winner == 'P1':
					turn_to_wins[r.turn_num].add(key)
			# Include missing turns with zeroes from turn 1 to max observed turn
			max_turn = max(turn_to_games.keys()) if turn_to_games else 1
			turn_labels = list(range(1, max_turn + 1))
			counts = [len(turn_to_games.get(t, set())) for t in turn_labels]
			win_rates = [
				(len(turn_to_wins.get(t, set())) / len(turn_to_games.get(t, set())) * 100)
				if len(turn_to_games.get(t, set())) > 0 else 0
				for t in turn_labels
			]
			winrate_chart = {
				'title': f"Game Win Rate & Occurrences",
				'chartTitle': 'Game Win Rate & Occurrences by Turn Number',
				'chartSubtitle': f"Casting Player: {'Opponent' if perspective == 'opponents' else 'Hero'} | Card: {selected_card}",
				'type': 'bar',
				'dualAxis': True,
				'xTitle': 'Turn Number',
				'yTitle': 'Win Rate %',
				'yRightTitle': 'Games',
				'yBeginAtZero': True,
				'yMin': 0,
				'yMax': 100,
				'legendDisplay': False,
				'data': {
					'labels': turn_labels,
					'datasets': [
						{
							'label': 'Win Rate %',
							'type': 'line',
							'data': win_rates,
							'yAxisID': 'y',
							'borderColor': '#0039A6',
							'backgroundColor': 'transparent',
							'tension': 0.25,
							'borderWidth': 2
						},
						{
							'label': 'Games',
							'type': 'bar',
							'data': counts,
							'yAxisID': 'y1',
							'backgroundColor': 'rgba(14,116,233,0.7)'
						}
					]
				}
			}

			# Attach Scryfall image URL on the chart payload
			image_url = get_card_image_url(selected_card)
			if image_url:
				winrate_chart['imageUrl'] = image_url
		else:
			# Placeholder card analysis panel when no card is selected
			winrate_chart = {
				'title': 'Card Analysis',
				'chartTitle': 'Select a Card to View Analysis',
				'chartSubtitle': 'Use the Card filter above or click a card in the tables.',
				'isPlaceholder': True,
				'type': 'bar',  # still provide a type for consistent rendering container
				'dualAxis': False,
				'xTitle': '',
				'yTitle': '',
				'legendDisplay': False,
				'imageUrl': '/static/images/mtgback.jpg',
				'data': {
					'labels': [],
					'datasets': []
				}
			}

		return {
			'metrics': [
				{
					'title': 'Unique Cards Played',
					'value': str(len(card_frequency_hero)),
					'subtitle': 'Different cards (non-land)',
					'type': 'count'
				},
				{
					'title': 'Most Played Card',
					'value': top_cards_hero[0][0] if top_cards_hero else 'None',
					'subtitle': f'{top_cards_hero[0][1]} times' if top_cards_hero else 'No data',
					'type': 'text'
				},
				{
					'title': 'Most Played Card Against',
					'value': top_cards_opp[0][0] if top_cards_opp else 'None',
					'subtitle': f'{top_cards_opp[0][1]} times' if top_cards_opp else 'No data',
					'type': 'text'
				}
			],
			'charts': ([winrate_chart] if winrate_chart else []),
			'tables': [
			],
			'table_grids': [
				{
					'type': '2x2',
					'title': 'Performance Overview',
					'grid': [
						[game1_table, games23_table]
					]
				}
			],
		}
		
	except Exception as e:
		debug_log(f"Error generating card analysis dashboard: {str(e)}")
		raise e

def generate_opponent_analysis_dashboard(filtered_query, filters):
	"""Generate opponent analysis dashboard data"""
	try:
		matches = filtered_query.all()
		
		# Basic opponent analysis
		opponent_stats = {}
		for match in matches:
			opp = match.p2
			if opp not in opponent_stats:
				opponent_stats[opp] = {'wins': 0, 'losses': 0, 'total': 0}
			
			opponent_stats[opp]['total'] += 1
			if match.match_winner == 'P1':
				opponent_stats[opp]['wins'] += 1
			else:
				opponent_stats[opp]['losses'] += 1
		
		# Calculate win rates
		for opp in opponent_stats:
			total = opponent_stats[opp]['total']
			wins = opponent_stats[opp]['wins']
			opponent_stats[opp]['win_rate'] = (wins / total * 100) if total > 0 else 0
		
		# Apply minimum match threshold filter
		min_threshold = int(filters.get('opponentThreshold', 1))  # Default to 1 if not specified
		filtered_opponent_stats = {opp: stats for opp, stats in opponent_stats.items() if stats['total'] >= min_threshold}
		
		# Check if any opponents meet the threshold
		if not filtered_opponent_stats:
			# Return dashboard indicating no opponents meet the threshold
			return {
				'metrics': [
					{'title': 'Unique Opponents', 'value': '0', 'subtitle': f'With {min_threshold}+ matches', 'type': 'count'},
					{'title': 'Most Faced Opponent', 'value': 'None', 'subtitle': f'No opponents with {min_threshold}+ matches', 'type': 'text'},
					{'title': 'Best Matchup', 'value': 'None', 'subtitle': f'No data', 'type': 'text'}
				],
				'charts': [
					{
						'title': 'Win Rate by Opponent',
						'type': 'bar',
						'data': {
							'labels': [],
							'datasets': [{
								'label': 'Win Rate %',
								'data': []
							}]
						}
					}
				],
				'tables': [
					{
						'title': 'Recent Match History',
						'headers': ['<center>Date</center>', '<center>Opponent</center>', '<center>Deck</center>', '<center>Opp. Deck</center>', '<center>Match Result</center>', '<center>Match Format</center>', '<center>Match Type</center>'],
						'height': '400px',
						'rows': [],
						'columnWidths': ['16%', '14%', '14%', '14%', '14%', '14%', '14%'],
						'cssClass': 'no-table-bottom-margin'
					}
				],
				'table_grids': [
					{
						'type': '2x2',
						'title': 'Performance Overview',
						'grid': [
							[
								{
									'title': 'Opponent Performance',
									'headers': ['<center>Opponent</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win% Against</center>'],
									'height': '300px',
									'rows': [],
									'columnWidths': ['31%', '23%', '23%', '23%']
								},
								{
									'title': 'Decks Played',
									'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win% Against</center>'],
									'height': '300px',
									'rows': [],
									'columnWidths': ['24%', '19%', '19%', '19%', '19%']
								}
							]
						]
					}
				]
			}
		
		# Sort by total matches
		top_opponents = sorted(filtered_opponent_stats.items(), key=lambda x: x[1]['total'], reverse=True)
		
		# Helper functions for formatting
		def match_result(p1_wins, p2_wins):
			if p1_wins == p2_wins:
				return f'NA {p1_wins}-{p2_wins}'
			elif p1_wins > p2_wins:
				return f'Win {p1_wins}-{p2_wins}'
			elif p2_wins > p1_wins:
				return f'Loss {p1_wins}-{p2_wins}'
		
		def format_date(date_str):
			"""Format date string to 'Month Day, Year' format"""
			if not date_str:
				return str(date_str)
			
			try:
				date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d-%H:%M').date()
				# Format as "July 6, 2025" (cross-platform compatible)
				formatted_date = date_obj.strftime('%B %d, %Y')
				# Remove leading zero from day if present (e.g., "July 06" -> "July 6")
				return formatted_date.replace(' 0', ' ')
			except ValueError:
				return date_str
		
		limited_formats = set(get_input_options().get('Limited Formats', []))
		def format_match_format(fmt, limited_format='NA'):
			fmt_norm = (fmt or 'NA').strip() if isinstance(fmt, str) else str(fmt or 'NA')
			lfmt_norm = (limited_format or '').strip() if isinstance(limited_format, str) else str(limited_format or '').strip()
			if fmt_norm in limited_formats and lfmt_norm and lfmt_norm.upper() != 'NA':
				return f'{fmt_norm} - {lfmt_norm}'
			return fmt_norm
		
		# Create opponent stats table
		def escape_for_js(text):
			"""Escape text for use in JavaScript onclick handlers"""
			return text.replace("'", "\\'").replace('"', '\\"').replace('\\', '\\\\')
		
		opponent_stats_table = {
			'title': 'Opponent Performance',
			'headers': ['<center>Opponent</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win% Against</center>'],
			'height': '300px',
			'rows': [[
				f'<a href="#" onclick="filterByOpponent(\'{escape_for_js(opp[0])}\'); return false;" style="color: var(--sky-blue); text-decoration: none; font-weight: 600; cursor: pointer;" onmouseover="this.style.textDecoration=\'underline\'" onmouseout="this.style.textDecoration=\'none\'">{opp[0]}</a>',
				f"<center>{opp[1]['wins']}</center>",
				f"<center>{opp[1]['losses']}</center>",
				f"<center>{opp[1]['win_rate']:.1f}%</center>"
			] for opp in top_opponents],
			'columnWidths': ['31%', '23%', '23%', '23%']
		}
		
		# Create match history table (most recent matches first)
		recent_matches = (
			filtered_query
			.outerjoin(Draft, (Draft.uid == Match.uid) & (Draft.draft_id == Match.draft_id))
			.add_entity(Draft)
			.order_by(Match.date.desc())
			.limit(25)
			.all()
		)
		
		def get_row_color(result_text):
			"""Get background color based on match result"""
			if 'Win' in result_text:
				return 'background-color: #dcfce7; border-left: 3px solid #16a34a;'  # Light green with green border
			elif 'Loss' in result_text:
				return 'background-color: #fef2f2; border-left: 3px solid #dc2626;'  # Light red with red border
			else:  # NA/Tie
				return 'background-color: #f3f4f6; border-left: 3px solid #6b7280;'  # Light grey with grey border
		
		match_history_table = {
			'title': 'Recent Match History',
			'headers': ['<center>Date</center>', '<center>Opponent</center>', '<center>Deck</center>', '<center>Opp. Deck</center>', '<center>Match Result</center>', '<center>Match Format</center>', '<center>Match Type</center>'],
			'height': '400px',
			'rows': [],
			'columnWidths': ['16%', '14%', '14%', '14%', '14%', '14%', '14%'],
			'cssClass': 'no-table-bottom-margin'
		}
		
		# Build recent match rows including draft format when present
		for match, draft in recent_matches:
			result_text = match_result(match.p1_wins, match.p2_wins)
			row_style = get_row_color(result_text)
			match_history_table['rows'].append([
				f"<center>{format_date(match.date)}</center>",
				f"<center>{match.p2}</center>",
				f"<center>{match.p1_subarch}</center>",
				f"<center>{match.p2_subarch}</center>",
				f"<center>{result_text}</center>",
				f"<center>{format_match_format(match.format, match.limited_format)}</center>",
				f"<center>{match.match_type}</center>",
				row_style  # Add row styling as the 7th element
			])
		
		# Observed Metagame
		total_matches = len(matches)
		if matches:
			import pandas as pd
			df = pd.DataFrame([{
				'p2_subarch': m.p2_subarch,
				'match_winner': m.match_winner
			} for m in matches])
			
			# Group by p2_subarch and calculate stats
			deck_stats = df.groupby('p2_subarch').agg({
				'match_winner': ['count', lambda x: sum(x == 'P1')]
			}).round(1)
			
			# Flatten column names
			deck_stats.columns = ['total_matches', 'wins']
			deck_stats['losses'] = deck_stats['total_matches'] - deck_stats['wins']
			deck_stats['win_pct'] = (deck_stats['wins'] / deck_stats['total_matches'] * 100).round(1)
			deck_stats['share_pct'] = (deck_stats['total_matches'] / total_matches * 100).round(1)
			deck_stats = deck_stats.sort_values(by='total_matches', ascending=False)
			
			# Reset index to get p2_subarch as a column
			deck_stats = deck_stats.reset_index()
			
			# Create table data for the return JSON
			observed_metagame_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win% Against</center>'],
				'height': '300px',
				'rows': [[
					row['p2_subarch'],
					f"<center>{row['wins'] + row['losses']} - ({row['share_pct']:.1f}%)</center>",
					f"<center>{int(row['wins'])}</center>",
					f"<center>{int(row['losses'])}</center>",
					f"<center>{row['win_pct']:.1f}%</center>"
				] for _, row in deck_stats.iterrows()],
				'columnWidths': ['24%', '19%', '19%', '19%', '19%']
			}
		else:
			observed_metagame_table = {
				'title': 'Decks Played',
				'headers': ['<center>Deck</center>', '<center>Share</center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win% Against</center>'],
				'height': '300px',
				'rows': [],
				'columnWidths': ['24%', '19%', '19%', '19%', '19%']
			}
		
		return {
			'metrics': [
				{
					'title': 'Unique Opponents',
					'value': str(len(filtered_opponent_stats)),
					'subtitle': f'With {min_threshold}+ matches',
					'type': 'count'
				},
				{
					'title': 'Most Faced Opponent',
					'value': top_opponents[0][0] if top_opponents else 'None',
					'subtitle': f'{top_opponents[0][1]["total"]} matches' if top_opponents else 'No data',
					'type': 'text'
				},
				{
					'title': 'Best Matchup',
					'value': max(filtered_opponent_stats.keys(), key=lambda x: filtered_opponent_stats[x]['win_rate']) if filtered_opponent_stats else 'None',
					'subtitle': f'{filtered_opponent_stats[max(filtered_opponent_stats.keys(), key=lambda x: filtered_opponent_stats[x]["win_rate"])]["win_rate"]:.1f}% win rate' if filtered_opponent_stats else 'No data',
					'type': 'text'
				}
			],
			'charts': [
			],
			'tables': [
				match_history_table
			],
			'table_grids': [
				{
					'type': '2x2',
					'title': 'Performance Overview',
					'grid': [
						[opponent_stats_table, observed_metagame_table]
					]
				}
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating opponent analysis dashboard: {str(e)}")
		raise e

def generate_game_data_dashboard(filtered_query, filters):
	"""Generate game data dashboard with hierarchical statistics"""
	try:		
		# Get games for filtered matches with joins
		games_query = db.session.query(Game).join(Match,
			(Game.uid == Match.uid) & (Game.match_id == Match.match_id) & (Game.p1 == Match.p1)
		).filter(
			Match.uid == current_user.uid,
			Match.p1 == current_user.username
		)
		
		# Apply the same filters as the filtered_query
		games_query = apply_dashboard_filters_to_game_query(games_query, filters)
		
		# Apply mulligans filters
		hero_mulls_filter = int(filters.get('heroMulls', 0))
		opp_mulls_filter = int(filters.get('oppMulls', 0))
		
		if hero_mulls_filter > 0:
			games_query = games_query.filter(Game.p1_mulls >= hero_mulls_filter)
		
		if opp_mulls_filter > 0:
			games_query = games_query.filter(Game.p2_mulls >= opp_mulls_filter)
		
		games = games_query.all()
		
		def calculate_stats(game_list, group_name):
			"""Calculate statistics for a group of games"""
			if not game_list:
				return [group_name, '<center>0</center>', '<center>0</center>', '<center>0.0%</center>', 
					   '<center>0.0</center>', '<center>0.0</center>', '<center>0.0</center>']
			
			wins = len([g for g in game_list if g.game_winner == 'P1'])
			losses = len(game_list) - wins
			win_pct = (wins / len(game_list) * 100) if game_list else 0
			
			avg_p1_mulls = sum([g.p1_mulls or 0 for g in game_list]) / len(game_list) if game_list else 0
			avg_p2_mulls = sum([g.p2_mulls or 0 for g in game_list]) / len(game_list) if game_list else 0
			avg_turns = sum([g.turns or 0 for g in game_list]) / len(game_list) if game_list else 0
			
			return [
				group_name,
				f'<center>{wins}</center>',
				f'<center>{losses}</center>', 
				f'<center>{win_pct:.1f}%</center>',
				f'<center>{avg_p1_mulls:.2f}</center>',
				f'<center>{avg_p2_mulls:.2f}</center>',
				f'<center>{avg_turns:.1f}</center>'
			]
		
		table_rows = []
		
		# Define styling for main category rows
		main_category_style = 'background-color: var(--bg-subtle); border-top: 3px solid var(--fg-muted); border-bottom: 3px solid var(--fg-muted); font-weight: 600;'
		
		# Overall stats
		overall_row = calculate_stats(games, '<strong>All Games</strong>')
		overall_row.append(main_category_style)
		table_rows.append(overall_row)
		
		# Game number breakdown for Overall
		for game_num in [1, 2, 3]:
			game_subset = [g for g in games if g.game_num == game_num]
			if game_subset:  # Only show if there are games
				table_rows.append(calculate_stats(game_subset, f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Game {game_num}'))
		
		# Play stats
		play_games = [g for g in games if g.on_play == 'P1']
		play_row = calculate_stats(play_games, '<strong>Play</strong>')
		play_row.append(main_category_style)
		table_rows.append(play_row)
		
		# Game number breakdown for Play
		for game_num in [1, 2, 3]:
			game_subset = [g for g in play_games if g.game_num == game_num]
			if game_subset:  # Only show if there are games
				table_rows.append(calculate_stats(game_subset, f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Game {game_num}'))
		
		# Draw stats
		draw_games = [g for g in games if g.on_draw == 'P1']
		draw_row = calculate_stats(draw_games, '<strong>Draw</strong>')
		draw_row.append(main_category_style)
		table_rows.append(draw_row)
		
		# Game number breakdown for Draw
		for game_num in [1, 2, 3]:
			game_subset = [g for g in draw_games if g.game_num == game_num]
			if game_subset:  # Only show if there are games
				table_rows.append(calculate_stats(game_subset, f'&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Game {game_num}'))
		
		# Calculate summary metrics
		total_games = len(games)
		total_wins = len([g for g in games if g.game_winner == 'P1'])
		overall_win_rate = (total_wins / total_games * 100) if total_games > 0 else 0
		
		play_win_rate = (len([g for g in play_games if g.game_winner == 'P1']) / len(play_games) * 100) if play_games else 0
		draw_win_rate = (len([g for g in draw_games if g.game_winner == 'P1']) / len(draw_games) * 100) if draw_games else 0
		
		game_performance_table = {
			'title': 'Game Performance Statistics',
			'headers': ['<center></center>', '<center>Wins</center>', '<center>Losses</center>', '<center>Win%</center>', '<center>Mulls/Game</center>', '<center>Opp Mulls/Game</center>', '<center>Turns/Game</center>'],
			'height': '425px',
			'rows': table_rows,
			'columnWidths': ['16%', '14%', '14%', '14%', '14%', '14%', '14%'],  # Option 1: Custom widths
			'cssClass': 'no-table-bottom-margin'
		}

		# Build stacked bar chart: Actions by Turn
		# Join Match → Game → Play with special counting rules
		value_expr = case(
				(Play.action == 'Attacks', func.coalesce(Play.attackers, 0)),
				(Play.action == 'Draws', func.coalesce(Play.cards_drawn, 0)),
				else_=1
		)

		play_query = db.session.query(
			Play.turn_num.label('turn_num'),
			Play.action.label('action'),
			func.sum(value_expr).label('action_count')
		).join(
				Game,
				(Game.uid == Play.uid) & (Game.match_id == Play.match_id) & (Game.game_num == Play.game_num)
		).join(
				Match,
				(Match.uid == Game.uid) & (Match.match_id == Game.match_id) & (Match.p1 == Game.p1)
		).filter(
				Match.uid == current_user.uid,
				Match.p1 == current_user.username
		)

		# Apply filters consistent with dashboards (expects Match already joined)
		play_query = apply_dashboard_filters_to_play_query(play_query, filters)

		# Apply chart-specific casting perspective (only affects this chart)
		chart_casting = (filters.get('chartCasting') or 'hero').lower()
		if chart_casting == 'hero':
				play_query = play_query.filter(Play.casting_player == current_user.username)
		elif chart_casting == 'opponents':
				play_query = play_query.filter(Play.casting_player != current_user.username)

		# Apply mulligan filters to the Play-based query as well
		if hero_mulls_filter > 0:
			play_query = play_query.filter(Game.p1_mulls >= hero_mulls_filter)
		if opp_mulls_filter > 0:
			play_query = play_query.filter(Game.p2_mulls >= opp_mulls_filter)

		play_query = play_query.group_by(Play.turn_num, Play.action).order_by(asc(Play.turn_num))
		action_rows = play_query.all()

		# Prepare chart data
		turn_labels = sorted({row.turn_num for row in action_rows if row.turn_num is not None})
		actions = sorted({row.action for row in action_rows if row.action is not None})

		# Map (action, turn) → count
		counts = {}
		for row in action_rows:
				if row.turn_num is None or row.action is None:
						continue
				counts[(row.action, row.turn_num)] = int(row.action_count or 0)

		datasets = []
		for action_name in actions:
				data_points = [counts.get((action_name, t), 0) for t in turn_labels]
				datasets.append({
						'label': action_name,
						'data': data_points
				})

		# Determine chart subtitle based on casting perspective
		if chart_casting == 'hero':
			chart_subtitle = 'Casting Player: Hero'
		elif chart_casting == 'opponents':
			chart_subtitle = 'Casting Player: Opponent'
		else:
			chart_subtitle = ''

		actions_by_turn_chart = {
			'title': 'Actions by Turn (Stacked)',
			'type': 'bar',
			'stacked': True,
			'xTitle': 'Turn Number',
			'yTitle': 'Game Actions',
			'chartTitle': 'Total Game Actions by Turn Number',
			'chartSubtitle': chart_subtitle,
			'chartPerspectiveControls': True,
			'chartCastingApplied': chart_casting,
			'data': {
				'labels': turn_labels,
				'datasets': datasets
			}
		}
   
		return {
			'metrics': [
				{
					'title': 'Overall Game Win Rate',
					'value': f'{overall_win_rate:.1f}%',
					'subtitle': f'{total_wins} wins, {total_games - total_wins} losses',
					'type': 'percentage'
				},
				{
					'title': 'On the Play',
					'value': f'{play_win_rate:.1f}%',
					'subtitle': f'{len(play_games)} games played',
					'type': 'percentage'
				},
				{
					'title': 'On the Draw',
					'value': f'{draw_win_rate:.1f}%',
					'subtitle': f'{len(draw_games)} games played',
					'type': 'percentage'
				}
			],
			'charts': [
				actions_by_turn_chart
			],
			'tables': [
				game_performance_table
			]
		}
		
	except Exception as e:
		debug_log(f"Error generating game data dashboard: {str(e)}")
		raise e

# Initialize these variables as None - they'll be loaded on demand
options = None
active_export_users = set()
export_locks_guard = threading.Lock()

@views.route('/api/table-status', methods=['GET'])
@login_required
def api_table_status():
	"""Get table status (empty/non-empty) for sidebar button management"""
	try:
		# Check if tables have data for current user
		match_count = Match.query.filter_by(uid=current_user.uid).count()
		draft_count = Draft.query.filter_by(uid=current_user.uid).count()
		removed_count = Removed.query.filter_by(uid=current_user.uid).count()
		game_actions_count = GameActions.query.filter_by(uid=current_user.uid).count()
		
		# Check if there are GameActions with valid match_ids (exist in Match table)
		valid_game_actions_count = 0
		if game_actions_count > 0:
			# Get all match_ids from GameActions for current user
			game_action_match_ids = db.session.query(GameActions.match_id).filter_by(uid=current_user.uid).distinct().all()
			game_action_match_ids = [row[0] for row in game_action_match_ids]
			
			# Check how many of these match_ids exist in Match table
			if game_action_match_ids:
				valid_match_ids = db.session.query(Match.match_id).filter(
					Match.uid == current_user.uid,
					Match.match_id.in_(game_action_match_ids)
				).all()
				valid_match_ids = [row[0] for row in valid_match_ids]
				
				# Count GameActions records that have valid match_ids
				if valid_match_ids:
					valid_game_actions_count = GameActions.query.filter(
						GameActions.uid == current_user.uid,
						GameActions.match_id.in_(valid_match_ids)
					).count()
		
		# Check if archive directory has files for reprocessing
		archive_files_count = 0
		archive_dir = os.path.join('local-dev', 'data', 'uploads', str(current_user.uid))
		if os.path.exists(archive_dir):
			all_files = os.listdir(archive_dir)
			# Count only GameLog and DraftLog files (not .meta files)
			for filename in all_files:
				if not filename.endswith('.meta'):
					log_type = get_logtype_from_filename(filename)
					if log_type in ['GameLog', 'DraftLog']:
						archive_files_count += 1
		
		return jsonify({
			'match_count': match_count,
			'draft_count': draft_count,
			'removed_count': removed_count,
			'game_actions_count': game_actions_count,
			'archive_files_count': archive_files_count,
			'status': {
				'matches_enabled': match_count > 0,
				'best_guess_enabled': match_count > 0,
				'drafts_enabled': draft_count > 0,
				'ignored_matches_enabled': removed_count > 0,
				'missing_winners_enabled': valid_game_actions_count > 0,
				'draft_ids_enabled': match_count > 0 and draft_count > 0,
				'reprocess_enabled': archive_files_count > 0,
				'export_enabled': match_count > 0 or draft_count > 0,
				'dashboards_enabled': match_count > 0 or draft_count > 0
			}
		})
	except Exception as e:
		debug_log(f"Error checking table status: {str(e)}")
		return jsonify({'error': 'Failed to check table status'}), 500
multifaced = None
all_decks = None
scryfall_image_cache = {}

def ensure_data_loaded():
	"""Load global data from cache (auto-refreshes when TTL expires)."""
	global options, multifaced, all_decks

	try:
		options = get_input_options()
	except Exception as e:
		debug_log(f"Warning: Could not load input options: {e}")
		options = {}

	try:
		multifaced = get_multifaced_cards()
	except Exception as e:
		debug_log(f"Warning: Could not load multifaced cards: {e}")
		multifaced = {}

	try:
		all_decks = get_all_decks()
	except Exception as e:
		debug_log(f"Warning: Could not load all decks: {e}")
		all_decks = {}

def refresh_reference_data_cache():
	"""Force refresh all cached reference datasets and update globals."""
	global options, multifaced, all_decks

	options = get_input_options(force_refresh=True)
	multifaced = get_multifaced_cards(force_refresh=True)
	all_decks = get_all_decks(force_refresh=True)

	return {
		'input_options_categories': len(options) if isinstance(options, dict) else 0,
		'multifaced_groups': len(multifaced) if isinstance(multifaced, dict) else 0,
		'all_decks_months': len(all_decks) if isinstance(all_decks, dict) else 0,
		'ttl_seconds': REFERENCE_CACHE_TTL_SECONDS,
	}

@views.route('/admin/refresh-reference-cache', methods=['POST'])
@login_required
def manual_refresh_reference_cache():
	"""Manually refresh reference caches (admin-only)."""
	admin_emails = {
		email.strip().lower()
		for email in os.environ.get('ADMIN_EMAILS', '').split(',')
		if email.strip()
	}
	current_email = (current_user.email or '').strip().lower()
	is_authorized = bool(getattr(current_user, 'is_admin', False)) or (current_email in admin_emails)

	if not is_authorized:
		return jsonify({'error': 'Forbidden'}), 403

	try:
		stats = refresh_reference_data_cache()
		return jsonify({
			'success': True,
			'message': 'Reference caches refreshed.',
			'refreshed_at_utc': datetime.datetime.utcnow().isoformat() + 'Z',
			'stats': stats,
		}), 200
	except Exception as e:
		debug_log(f"Error refreshing reference cache: {e}")
		return jsonify({'error': 'Failed to refresh reference cache'}), 500

def get_card_image_url(card_name: str):
    """Fetch a Scryfall image URL for a given exact card name with simple caching.
    Handles MDFC/split/adventure by falling back to first face.
    Returns a string URL or None on failure.
    """
    try:
        if not card_name:
            return None
        key = card_name.strip().lower()
        if key in scryfall_image_cache:
            return scryfall_image_cache[key]

        base = 'https://api.scryfall.com/cards/named'
        # First try exact match
        try:
            r = requests.get(base, params={'exact': card_name}, timeout=5)
        except Exception:
            r = None
        if not r or r.status_code != 200:
            # Fallback to fuzzy
            try:
                r = requests.get(base, params={'fuzzy': card_name}, timeout=5)
            except Exception:
                r = None
        if not r or r.status_code != 200:
            return None
        data = r.json()
        image_url = None
        if isinstance(data, dict):
            if 'image_uris' in data and isinstance(data['image_uris'], dict):
                # Prefer normal → large → border_crop
                image_url = data['image_uris'].get('normal') or data['image_uris'].get('large') or data['image_uris'].get('border_crop')
            elif 'card_faces' in data and isinstance(data['card_faces'], list) and data['card_faces']:
                faces0 = data['card_faces'][0]
                if 'image_uris' in faces0 and isinstance(faces0['image_uris'], dict):
                    image_url = faces0['image_uris'].get('normal') or faces0['image_uris'].get('large') or faces0['image_uris'].get('border_crop')
        if image_url:
            scryfall_image_cache[key] = image_url
            return image_url
        return None
    except Exception as e:
        debug_log(f"Scryfall image fetch failed for '{card_name}': {e}")
        return None

@views.route('/test_email')
@login_required 
def test_email():
	"""Test email configuration"""
	try:
		from app import create_app
		app = create_app()
		
		with app.app_context():
			debug_log("🔍 Testing email configuration...")
			debug_log(f"📧 MAIL_SERVER: {app.config.get('MAIL_SERVER')}")
			debug_log(f"📧 MAIL_USERNAME: {app.config.get('MAIL_USERNAME')}")
			debug_log(f"📧 MAIL_PORT: {app.config.get('MAIL_PORT')}")
			debug_log(f"📧 MAIL_USE_TLS: {app.config.get('MAIL_USE_TLS')}")
			debug_log(f"📧 MAIL_USE_SSL: {app.config.get('MAIL_USE_SSL')}")
			
			mail = app.extensions['mail']
			msg = Message(
				'MTGO-DB Test Email', 
				sender=app.config.get('MAIL_USERNAME'), 
				recipients=[current_user.email]
			)
			msg.body = 'This is a test email from MTGO-DB to verify email configuration.'
			
			try:
				mail.send(msg)
				debug_log("📧 Test email sent successfully!")
				flash('Test email sent successfully! Check your inbox.', 'success')
			except Exception as e:
				debug_log(f"📧 Test email failed: {e}")
				flash(f'Email test failed: {e}', 'error')
				
	except Exception as e:
		debug_log(f"📧 Email test error: {e}")
		flash(f'Email test error: {e}', 'error')
	
	return redirect(url_for('views.profile'))

@views.route('/view_debug_log')
@login_required
def view_debug_log():
	"""View debug log file"""
	try:
		log_file = os.path.join('local-dev', 'data', 'logs', 'debug_log.txt')
		if os.path.exists(log_file):
			with open(log_file, 'r', encoding='utf-8') as f:
				log_content = f.read()
			return f"<pre>{log_content}</pre>"
		else:
			return "Debug log file not found."
	except Exception as e:
		return f"Error reading debug log: {e}"

# Modern API endpoints for Table functionality
@views.route('/api/table/<table_name>/<int:page_num>')
@login_required
def api_table_data(table_name, page_num):
	"""Get table data with pagination"""
	try:		
		# Determine which table to query
		if table_name.lower() == 'matches':
			total_count = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).count()
			query = Match.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Match.date))
		elif table_name.lower() == 'games':
			total_count = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).count()
			query = Game.query.filter_by(uid=current_user.uid, p1=current_user.username).order_by(desc(Game.match_id), Game.game_num)
		elif table_name.lower() == 'plays':
			total_count = Play.query.filter_by(uid=current_user.uid).count()
			query = Play.query.filter_by(uid=current_user.uid).order_by(desc(Play.match_id), Play.game_num, Play.play_num)
		elif table_name.lower() == 'drafts':
			total_count = Draft.query.filter_by(uid=current_user.uid).count()
			query = Draft.query.filter_by(uid=current_user.uid).order_by(desc(Draft.date))
		elif table_name.lower() == 'picks':
			total_count = Pick.query.filter_by(uid=current_user.uid).count()
			query = Pick.query.filter_by(uid=current_user.uid).order_by(desc(Pick.draft_id), Pick.pick_ovr)
		else:
			return jsonify({'error': 'Invalid table name'}), 400
		
		# Calculate pagination
		total_pages = math.ceil(total_count / page_size)
		if page_num < 1 or page_num > total_pages:
			return jsonify({'error': 'Invalid page number'}), 400
		
		# Get the data for this page
		offset = (page_num - 1) * page_size
		records = query.offset(offset).limit(page_size).all()
		
		# Convert to JSON-serializable format
		table_data = [record.as_dict() for record in records]
		
		return jsonify({
			'table_name': table_name,
			'page_num': page_num,
			'total_pages': total_pages,
			'total_count': total_count,
			'page_size': page_size,
			'data': table_data,
			'has_previous': page_num > 1,
			'has_next': page_num < total_pages
		})
		
	except Exception as e:
		debug_log(f"Error in api_table_data: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/table/<table_name>/drill/<row_id>/<int:game_num>')
@login_required
def api_table_drill(table_name, row_id, game_num):
	"""Get drill-down table data (filtered child table)"""
	try:
		if table_name.lower() == 'games':
			records = Game.query.filter_by(
				uid=current_user.uid, 
				match_id=row_id, 
				p1=current_user.username
			).order_by(Game.game_num).all()
		elif table_name.lower() == 'plays':
			records = Play.query.filter_by(
				uid=current_user.uid, 
				match_id=row_id, 
				game_num=game_num
			).order_by(Play.play_num).all()
		elif table_name.lower() == 'picks':
			records = Pick.query.filter_by(
				uid=current_user.uid, 
				draft_id=row_id
			).order_by(Pick.pick_ovr).all()
		else:
			return jsonify({'error': 'Invalid drill-down table'}), 400
		
		# Convert to JSON-serializable format
		table_data = [record.as_dict() for record in records]
		
		return jsonify({
			'table_name': table_name,
			'filtered_by': {'row_id': row_id, 'game_num': game_num},
			'data': table_data,
			'total_count': len(table_data)
		})
		
	except Exception as e:
		debug_log(f"Error in api_table_drill: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/card-image', methods=['GET'])
@login_required
def api_card_image():
	"""Resolve a card name to a Scryfall image URL."""
	card_name = (request.args.get('name') or '').strip()
	if not card_name:
		return jsonify({'image_url': None, 'card_name': ''}), 200
	try:
		image_url = get_card_image_url(card_name)
		return jsonify({'image_url': image_url, 'card_name': card_name}), 200
	except Exception as e:
		debug_log(f"Error in api_card_image for '{card_name}': {str(e)}")
		return jsonify({'image_url': None, 'card_name': card_name}), 200

@views.route('/api/match/<match_id>/details')
@login_required
def api_match_details(match_id):
	"""Get detailed match information for revision modal"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		# Get match data
		match = Match.query.filter_by(
			uid=current_user.uid, 
			match_id=match_id, 
			p1=current_user.username
		).first()
		
		if not match:
			return jsonify({'error': 'Match not found'}), 404
		
		# Get cards played data
		cards = CardsPlayed.query.filter_by(
			uid=current_user.uid, 
			match_id=match_id
		).first()
		
		response_data = match.as_dict()
		
		if cards:
			cards_data = cards.as_dict()
			response_data.update({
				'casting_player1': cards_data.get('casting_player1'),
				'casting_player2': cards_data.get('casting_player2'),
				'lands1': cards_data.get('lands1', []),
				'lands2': cards_data.get('lands2', []),
				'plays1': cards_data.get('plays1', []),
				'plays2': cards_data.get('plays2', [])
			})
		
		return jsonify(response_data)
		
	except Exception as e:
		debug_log(f"Error in api_match_details: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/revise', methods=['POST'])
@login_required
def api_match_revise():
	"""Revise a single match"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_id = data.get('match_id')
		if not match_id:
			return jsonify({'error': 'Missing match_id'}), 400
		
		# Get the match
		matches = Match.query.filter_by(
			uid=current_user.uid,
			match_id=match_id
		).all()
		
		if not matches:
			return jsonify({'error': 'Match not found'}), 404
		
		# Small helper to strip strings
		clean = lambda v: v.strip() if isinstance(v, str) else v

		# Ensure shared option data is loaded (not strictly needed here)
		ensure_data_loaded()

		# Update match data
		for match in matches:
			# Pre-clean inputs
			p1_arch_in = clean(data.get('p1_arch'))
			p1_subarch_in = clean(data.get('p1_subarch'))
			p2_arch_in = clean(data.get('p2_arch'))
			p2_subarch_in = clean(data.get('p2_subarch'))
			format_in = clean(data.get('format'))
			limited_format_in = clean(data.get('limited_format'))
			match_type_in = clean(data.get('match_type'))

			if match.p1 == current_user.username:
				if p1_arch_in: match.p1_arch = p1_arch_in
				if p1_subarch_in: match.p1_subarch = p1_subarch_in
				if p2_arch_in: match.p2_arch = p2_arch_in
				if p2_subarch_in: match.p2_subarch = p2_subarch_in
			else:
				if p1_arch_in: match.p1_arch = p2_arch_in
				if p1_subarch_in: match.p1_subarch = p2_subarch_in
				if p2_arch_in: match.p2_arch = p1_arch_in
				if p2_subarch_in: match.p2_subarch = p1_subarch_in
			
			if format_in: match.format = format_in
			if limited_format_in: match.limited_format = limited_format_in
			if match_type_in: match.match_type = match_type_in
		
		try:
			db.session.commit()
			return jsonify({'success': True, 'message': 'Match updated successfully'})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing match revision: {str(e)}")
			return jsonify({'error': 'Failed to update match'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_revise: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/revise-multi', methods=['POST'])
@login_required
def api_match_revise_multi():
	"""Revise multiple matches"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		# Debug logging
		debug_log(f"Multi-revision data received: {data}")
		
		match_ids = data.get('match_ids', [])
		field_to_change = data.get('field_to_change')
		
		if not match_ids or not field_to_change:
			debug_log(f"Missing required fields - match_ids: {match_ids}, field_to_change: {field_to_change}")
			return jsonify({'error': 'Missing required fields'}), 400
		
		# Get the matches
		matches = Match.query.filter(
			Match.match_id.in_(match_ids),
			Match.uid == current_user.uid
		).all()
		
		if not matches:
			return jsonify({'error': 'No matches found'}), 404
		
		# Small helper to strip strings
		clean = lambda v: v.strip() if isinstance(v, str) else v

		# Ensure shared option data is loaded and create a safe local reference
		ensure_data_loaded()
		safe_options = options if isinstance(options, dict) else {}

		# Apply changes based on field type
		for match in matches:
			if field_to_change == 'P1 Deck':
				if match.p1 == current_user.username:
					p1_arch_in = clean(data.get('p1_arch'))
					p1_subarch_in = clean(data.get('p1_subarch'))
					if match.p1_arch != 'Limited' and p1_arch_in:
						match.p1_arch = p1_arch_in
					if p1_subarch_in:
						match.p1_subarch = p1_subarch_in
				else:
					p1_arch_in = clean(data.get('p1_arch'))
					p1_subarch_in = clean(data.get('p1_subarch'))
					if match.p2_arch != 'Limited' and p1_arch_in:
						match.p2_arch = p1_arch_in
					if p1_subarch_in:
						match.p2_subarch = p1_subarch_in
			
			elif field_to_change == 'P2 Deck':
				if match.p1 == current_user.username:
					p2_arch_in = clean(data.get('p2_arch'))
					p2_subarch_in = clean(data.get('p2_subarch'))
					if match.p2_arch != 'Limited' and p2_arch_in:
						match.p2_arch = p2_arch_in
					if p2_subarch_in:
						match.p2_subarch = p2_subarch_in
				else:
					p2_arch_in = clean(data.get('p2_arch'))
					p2_subarch_in = clean(data.get('p2_subarch'))
					if match.p1_arch != 'Limited' and p2_arch_in:
						match.p1_arch = p2_arch_in
					if p2_subarch_in:
						match.p1_subarch = p2_subarch_in
			
			elif field_to_change == 'Format':
				fmt_in = clean(data.get('format'))
				lfmt_in = clean(data.get('limited_format'))
				if fmt_in:
					match.format = fmt_in
				if lfmt_in:
					match.limited_format = lfmt_in
				
				# Handle Limited format archetype changes
				if fmt_in in safe_options.get('Limited Formats', []):
					match.p1_arch = 'Limited'
					match.p2_arch = 'Limited'
				else:
					if match.p1_arch == 'Limited':
						match.p1_arch = 'NA'
					if match.p2_arch == 'Limited':
						match.p2_arch = 'NA'
			
			elif field_to_change == 'Match Type':
				mt_in = clean(data.get('match_type'))
				if mt_in:
					match.match_type = mt_in
		
		try:
			db.session.commit()
			return jsonify({
				'success': True, 
				'message': f'Updated {len(matches)} matches successfully'
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing multi-match revision: {str(e)}")
			return jsonify({'error': 'Failed to update matches'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_revise_multi: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500

@views.route('/api/match/remove', methods=['POST'])
@login_required
def api_match_remove():
	"""Remove matches (with optional ignore)"""
	if request.headers.get('X-Requested-By') != 'MTGO-Tracker':
		return jsonify({'error': 'Forbidden'}), 403
	
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_ids = data.get('match_ids', [])
		remove_type = data.get('remove_type', 'Remove')  # 'Remove' or 'Ignore'
		
		if not match_ids:
			return jsonify({'error': 'No match IDs provided'}), 400
		
		match_count = 0
		game_count = 0
		play_count = 0
		proc_dt = datetime.datetime.now(pytz.utc).astimezone(pytz.timezone('US/Pacific'))
		
		for match_id in match_ids:
			# Get match date BEFORE deletion (needed for ignored list)
			match_record = Match.query.filter_by(uid=current_user.uid, match_id=match_id).first()
			mtime = match_record.date if match_record else None
			
			# Count records before deletion
			match_count += Match.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			game_count += Game.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			play_count += Play.query.filter_by(uid=current_user.uid, match_id=match_id).count()
			
			# Delete records
			Match.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			Game.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			Play.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			
			# Add to ignored list if requested
			if remove_type == 'Ignore' and mtime:
				new_ignore = Removed(uid=current_user.uid, match_id=match_id, date=mtime, reason='Ignored', proc_dt=proc_dt)
				db.session.add(new_ignore)
		
		try:
			db.session.commit()
			return jsonify({
				'success': True,
				'message': f'{match_count} Matches removed, {game_count} Games removed, {play_count} Plays removed.',
				'removed_counts': {
					'matches': match_count,
					'games': game_count,
					'plays': play_count
				}
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing match removal: {str(e)}")
			return jsonify({'error': 'Failed to remove matches'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_match_remove: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500


@views.route('/api/ignored/remove', methods=['POST'])
@login_required
def api_ignored_remove():
	"""Remove matches from ignored list (unignore them)"""
	try:
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400
		
		match_ids = data.get('match_ids', [])
		
		if not match_ids:
			return jsonify({'error': 'No match IDs provided'}), 400
		
		removed_count = 0
		
		for match_id in match_ids:
			# Remove from ignored list
			removed_records = Removed.query.filter_by(uid=current_user.uid, match_id=match_id).delete()
			removed_count += removed_records
		
		try:
			db.session.commit()
			return jsonify({
				'success': True,
				'message': f'{removed_count} match(es) removed from ignored list.',
				'removed_count': removed_count
			})
		except Exception as e:
			db.session.rollback()
			debug_log(f"Error committing ignored removal: {str(e)}")
			return jsonify({'error': 'Failed to remove from ignored list'}), 500
		
	except Exception as e:
		debug_log(f"Error in api_ignored_remove: {str(e)}")
		return jsonify({'error': 'Internal server error'}), 500