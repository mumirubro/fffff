import os
import random
import requests
import logging
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token
TOKEN = "7767060683:AAFINLNZpewqW3GlfuxWmn_ZS2y8-FpKEC4"

# Conversation states
SELECT_BIN_TYPE, SELECT_DIGITS = range(2)

# Bin types
BIN_TYPES = {
    '1': 'Visa 4',
    '2': 'Mastercard 5',
    '3': 'American Express 3',
    '4': 'Discover 6'
}

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Welcome to the BIN Bot!\n\n"
        "Available commands:\n"
        "/gbin - Generate BINs\n"
        "/bin - Check BINs\n"
        "/gen - Generate CCs\n"
    )

def gbin(update: Update, context: CallbackContext) -> int:
    try:
        amount = int(context.args[0])
        if amount <= 0:
            update.message.reply_text("Please provide a positive number greater than 0.")
            return ConversationHandler.END
            
        context.user_data['amount'] = amount
        reply_text = "Which BIN type do you want?\n"
        for key, value in BIN_TYPES.items():
            reply_text += f"{key}. {value}\n"
        
        update.message.reply_text(reply_text)
        return SELECT_BIN_TYPE
        
    except (IndexError, ValueError):
        update.message.reply_text("Usage: /gbin <amount>")
        return ConversationHandler.END

def select_bin_type(update: Update, context: CallbackContext) -> int:
    choice = update.message.text.strip()
    if choice not in BIN_TYPES:
        update.message.reply_text("Invalid choice. Please select a number from the options.")
        return SELECT_BIN_TYPE
        
    bin_prefix = BIN_TYPES[choice].split()[-1]
    context.user_data['bin_prefix'] = bin_prefix
    update.message.reply_text("How many digits do you need in the BIN? (5 or 6)")
    return SELECT_DIGITS

def select_digits(update: Update, context: CallbackContext) -> int:
    digits = update.message.text.strip()
    if digits not in ['5', '6']:
        update.message.reply_text("Please enter either 5 or 6 for the digit count.")
        return SELECT_DIGITS
        
    digits = int(digits)
    amount = context.user_data['amount']
    bin_prefix = context.user_data['bin_prefix']
    
    bins = []
    for _ in range(amount):
        remaining_digits = digits - len(bin_prefix)
        random_part = ''.join([str(random.randint(0, 9)) for _ in range(remaining_digits)])
        bins.append(bin_prefix + random_part)
    
    # Send as text file if more than 10, otherwise as message
    if amount <= 10:
        update.message.reply_text("\n".join(bins))
    else:
        with open('bins.txt', 'w') as f:
            f.write("\n".join(bins))
        with open('bins.txt', 'rb') as f:
            update.message.reply_document(document=f, filename='bins.txt')
        os.remove('bins.txt')
    
    return ConversationHandler.END

def bin_command(update: Update, context: CallbackContext) -> None:
    context.user_data['bins_to_check'] = []
    update.message.reply_text("Please send me BINs to check (one per line) or a .txt file with BINs.")

def handle_bin_input(update: Update, context: CallbackContext) -> None:
    if update.message.document:
        # Handle file upload
        file = update.message.document.get_file()
        file.download('bins_to_check.txt')
        with open('bins_to_check.txt', 'r') as f:
            bins = [line.strip() for line in f.readlines() if line.strip()]
        os.remove('bins_to_check.txt')
    else:
        # Handle text input
        bins = [line.strip() for line in update.message.text.split('\n') if line.strip()]
    
    context.user_data['bins_to_check'] = bins
    update.message.reply_text(f"Received {len(bins)} BIN(s) to check. Send /mbin to process them.")

def mbin(update: Update, context: CallbackContext) -> None:
    if 'bins_to_check' not in context.user_data or not context.user_data['bins_to_check']:
        update.message.reply_text("No BINs to check. Please send BINs first.")
        return
    
    bins = context.user_data['bins_to_check']
    results = []
    
    for bin_num in bins:
        if len(bin_num) < 6:
            results.append(f"⚠️ Invalid BIN format for {bin_num}. BIN must be at least 6 digits.")
            continue
            
        first_six = bin_num[:6]
        try:
            response = requests.get(f"https://bins.antipublic.cc/bins/{first_six}")
            data = response.json()
            
            if data.get('error'):
                results.append(f"⚠️ Invalid BIN: {first_six}")
            else:
                result_text = (
                    f"▐ 𝗩𝗔𝗟𝗜𝗗 𝗕𝗜𝗡 ✅️ ▐\n\n"
                    f"𝗕𝗜𝗡 ⇾ {first_six}\n\n"
                    f"𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {data.get('brand', 'N/A')}\n"
                    f"𝗖𝘂𝗿𝗿𝗲𝗻𝗰𝘆: {data.get('currency', 'N/A')}\n"
                    f"𝗕𝗮𝗻𝗸: {data.get('bank', 'N/A')}\n"
                    f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {data.get('country', 'N/A')} ({data.get('country_code', 'N/A')})\n"
                    f"𝗥𝗲𝗾 ⌁ @{update.message.from_user.username}"
                )
                results.append(result_text)
                
        except Exception as e:
            results.append(f"⚠️ Error checking BIN {first_six}: {str(e)}")
    
    # Send results (in chunks if too long)
    chunk_size = 5
    for i in range(0, len(results), chunk_size):
        chunk = results[i:i+chunk_size]
        update.message.reply_text("\n\n".join(chunk))

def gen(update: Update, context: CallbackContext) -> None:
    try:
        if len(context.args) < 2:
            raise ValueError
        
        bin_num = context.args[0]
        amount = int(context.args[1])
        
        if amount <= 0:
            update.message.reply_text("Amount must be greater than 0.")
            return
            
        # Determine card length based on BIN
        if bin_num.startswith('3'):
            card_length = 15  # Amex
        elif bin_num.startswith(('30', '36', '38', '39')):
            card_length = 14  # Diners Club (some)
        else:
            card_length = 16  # Visa, MC, Discover, etc.
            
        # Generate cards
        cards = []
        for _ in range(amount):
            remaining_length = card_length - len(bin_num)
            card_number = bin_num + ''.join([str(random.randint(0, 9)) for _ in range(remaining_length)])
            exp_month = str(random.randint(1, 12)).zfill(2)
            exp_year = str(random.randint(2023, 2030))
            cvv = ''.join([str(random.randint(0, 9)) for _ in range(3)])
            cards.append(f"{card_number}|{exp_month}|{exp_year}|{cvv}")
        
        # Prepare info (will be empty as we don't have API for this in /gen)
        info_text = (
            f"Card Generator  \n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"[ᛋ] Bin: {bin_num}xxxx|{random.randint(1,12):02d}|20{random.randint(23,30)}|rnd\n"
            f"━━━━━━━━━━━━━━━━━\n"
        )
        
        if amount <= 10:
            # Send as formatted message
            message = info_text + "\n".join(cards) + (
                f"\n━━━━━━━━━━━━━━━━━\n"
                f"[ᛋ] Info: \n"
                f"[ᛋ] Bank: \n"
                f"[ᛋ] Country: \n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"[ᛋ] Generate by: @{update.message.from_user.username}"
            )
            update.message.reply_text(message)
        else:
            # Send as file
            with open('cards.txt', 'w') as f:
                f.write("\n".join(cards))
            with open('cards.txt', 'rb') as f:
                update.message.reply_document(
                    document=f,
                    filename='cards.txt',
                    caption=f"Generated {amount} cards from BIN {bin_num}\nGenerated by: @{update.message.from_user.username}"
                )
            os.remove('cards.txt')
            
    except (IndexError, ValueError):
        update.message.reply_text("Usage: /gen <bin> <amount>")

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

def main() -> None:
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Add conversation handler for /gbin command
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('gbin', gbin)],
        states={
            SELECT_BIN_TYPE: [MessageHandler(Filters.text & ~Filters.command, select_bin_type)],
            SELECT_DIGITS: [MessageHandler(Filters.text & ~Filters.command, select_digits)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("bin", bin_command))
    dispatcher.add_handler(MessageHandler(Filters.text | Filters.document, handle_bin_input))
    dispatcher.add_handler(CommandHandler("mbin", mbin))
    dispatcher.add_handler(CommandHandler("gen", gen))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()