from hashlib import sha256
from inputimeout import inputimeout, TimeoutOccurred
import tabulate, copy, time, datetime, requests, sys, os
from sys import platform
from captcha import captcha_builder

# 9896698975

BOOKING_URL = "https://cdn-api.co-vin.in/api/v2/appointment/schedule"
BENEFICIARIES_URL = "https://cdn-api.co-vin.in/api/v2/appointment/beneficiaries"
CALENDAR_URL = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={0}&date={1}"
CAPTCHA_URL = "https://cdn-api.co-vin.in/api/v2/auth/getRecaptcha"
WARNING_BEEP_DURATION = (1000, 2000)

mandatory_request_header = {
    "authority": "cdn-api.co-vin.in",
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "origin": "https://selfregistration.cowin.gov.in",
    "referer": "https://selfregistration.cowin.gov.in/appointment",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "Remote Address": "[2600:9000:213c:9400:6:3338:2bc0:93a1]:443",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36"
}
try:
    import winsound

except ImportError:
    import os


def beep(freq, duration):
    # apt-get install beep  --> install beep package on linux distros before running
    if platform == "darwin":
        for i in range(3):
            os.system('say Fire in the Hole')
            time.sleep(2)
    elif platform == "win32":
        winsound.Beep(freq, duration)
    else:
        print("JEEEELOOOO!!!")


def display_table(dict_list):
    """
    This function
        1. Takes a list of dictionary
        2. Add an Index column, and
        3. Displays the data in tabular format
    """
    header = ['idx'] + list(dict_list[0].keys())
    rows = [[idx + 1] + list(x.values()) for idx, x in enumerate(dict_list)]
    print(tabulate.tabulate(rows, header, tablefmt='grid'))


def check_calendar(request_header, vaccine_type, district_dtls, minimum_slots, min_age_booking, dose=1):
    """
    This function
        1. Takes details required to check vaccination calendar
        2. Filters result by minimum number of slots available
        3. Returns False if token is invalid
        4. Returns list of vaccination centers & slots if available
    """
    try:
        print('===================================================================================')
        tomorrow = _get_tomorrow()

        base_url = CALENDAR_URL
        if vaccine_type:
            base_url += f"&vaccine={vaccine_type}"

        options = []
        for district in district_dtls:
            request_header.update(mandatory_request_header)
            resp = requests.get(base_url.format(district['district_id'], tomorrow), headers=request_header)

            if resp.status_code == 401:
                print('TOKEN INVALID')
                return False

            elif resp.status_code == 200:
                resp = resp.json()
                options.extend(parse_calender_response(resp, minimum_slots, min_age_booking, dose))
            else:
                pass

        return options

    except Exception as e:
        print(str(e))
        beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def _get_tomorrow():
    today = datetime.datetime.today()
    return (today + datetime.timedelta(days=1)).strftime("%d-%m-%Y")


def parse_calender_response(resp, minimum_slots=1, min_age_booking=18, dose=1):
    print(
        f"Centers available from {_get_tomorrow()} as of {datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')}: {len(resp['centers'])}")
    options = []
    dose_field = 'available_capacity_dose1' if dose==1 else 'available_capacity_dose2'
    if len(resp['centers']) >= 0:
        for center in resp['centers']:
            for session in center['sessions']:
                if (session[dose_field] >= minimum_slots) \
                        and (session['min_age_limit'] <= min_age_booking):
                    out = {
                        'name': center['name'],
                        'district': center['district_name'],
                        'center_id': center['center_id'],
                        'available': session['available_capacity'],
                        'date': session['date'],
                        'slots': session['slots'],
                        'session_id': session['session_id']
                    }
                    options.append(out)
        print(options)
    else:
        pass
    return options

def generate_captcha(request_header):
    print('================================= GETTING CAPTCHA ==================================================')
    resp = requests.post(CAPTCHA_URL, headers=request_header)
    print(f'Captcha Response Code: {resp.status_code}')

    if resp.status_code == 200:

        return captcha_builder(resp.json())


def book_appointment(request_header, details):
    """
    This function
        1. Takes details in json format
        2. Attempts to book an appointment using the details
        3. Returns True or False depending on Token Validity
    """
    valid_captcha = True
    while valid_captcha:
        try:
            # beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
            beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
            captcha = generate_captcha(request_header)
            details['captcha'] = captcha
            print('================================= ATTEMPTING BOOKING ==================================================')
            request_header.update(mandatory_request_header)
            resp = requests.post(BOOKING_URL, headers=request_header, json=details)
            print(f'Booking Response Code: {resp.status_code}')
            print(f'Booking Response : {resp.text}')

            if resp.status_code == 401:
                print('TOKEN INVALID')
                return False

            elif resp.status_code == 200:
                beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])
                print('##############    BOOKED!  ##############')

            else:
                print(f'Response: {resp.status_code} : {resp.text}')
                return True

        except Exception as e:
            print(str(e))
            beep(WARNING_BEEP_DURATION[0], WARNING_BEEP_DURATION[1])


def check_and_book(request_header, beneficiary_dtls, district_dtls, **kwargs):
    """
    This function
        1. Checks the vaccination calendar for available slots,
        2. Lists all viable options,
        3. Takes user's choice of vaccination center and slot,
        4. Calls function to book appointment, and
        5. Returns True or False depending on Token Validity
    """
    try:
        min_age_booking = get_min_age(beneficiary_dtls)
        vaccine_type = [beneficiary['vaccine'] for beneficiary in beneficiary_dtls][0]

        minimum_slots = kwargs['min_slots']
        refresh_freq = kwargs['ref_freq']

        options = check_calendar(request_header, vaccine_type, district_dtls, minimum_slots, min_age_booking, kwargs['dose'])

        if isinstance(options, bool):
            return False

        options = sorted(options,
                         key=lambda k: (k['district'].lower(),
                                        k['name'].lower(),
                                        datetime.datetime.strptime(k['date'], "%d-%m-%Y"))
                         )
        return ask_and_book(options, request_header, beneficiary_dtls, **kwargs)
    except TimeoutOccurred:
        time.sleep(1)
        return True


def ask_and_book(options, request_header, beneficiary_dtls, **kwargs):
    minimum_slots = kwargs['min_slots']
    refresh_freq = kwargs['ref_freq']
    center = kwargs['center']
    vaccine_type = [beneficiary['vaccine'] for beneficiary in beneficiary_dtls][0]
    tmp_options = copy.deepcopy(options)
    center_available = False
    center_index = 0
    if len(tmp_options) > 0:
        cleaned_options_for_display = []
        i = 0
        for item in tmp_options:
            if center in item['name']:
                center_available = True
                center_index = i
            item.pop('session_id', None)
            item.pop('center_id', None)
            cleaned_options_for_display.append(item)
            i += 1

        display_table(cleaned_options_for_display)

        if not center_available:
            choice = inputimeout(
                prompt='----------> Wait 20 seconds for updated options OR \n----------> Enter a choice e.g: 1.4 for (1st center 4th slot): ',
                timeout=20)
        else:
            choice = "auto"

    else:
        for i in range(refresh_freq, 0, -1):
            msg = f"No viable options. Next update in {i} seconds.."
            print(msg, end="\r", flush=True)
            sys.stdout.flush()
            time.sleep(1)
        choice = '.'

    return_val = False
    if choice == '.':
        return_val = True
    elif choice == "auto":
        for center in range(1, center_index, 1):
            for slot in range(4, 0, -1):
                if _book("{}.{}".format(center, slot), beneficiary_dtls, vaccine_type, options, request_header):
                    print("Booked {}.{}".format(center, slot))
                    return_val = True
                    break
                else:
                    print("Couldn't Book {}.{}".format(center, slot))
    else:
        return_val = _book(choice, beneficiary_dtls, vaccine_type, options, request_header)
    return return_val


def _book(choice, beneficiary_dtls, vaccine_type, options, request_header):
    try:
        choice = choice.split('.')
        choice = [int(item) for item in choice]
        print(f'============> Got Choice: Center #{choice[0]}, Slot #{choice[1]}')

        new_req = {
            'beneficiaries': [beneficiary['beneficiary_reference_id'] for beneficiary in beneficiary_dtls],
            'dose': 2 if vaccine_type else 1,
            'center_id': options[choice[0] - 1]['center_id'],
            'session_id': options[choice[0] - 1]['session_id'],
            'slot': options[choice[0] - 1]['slots'][choice[1] - 1]
        }

        print(f'Booking with info: {new_req}')
        return book_appointment(request_header, new_req)

    except IndexError:
        print("============> Invalid Option!")
        pass


def book_by_pincode(pincode, request_header, beneficiary_dtls, **kwargs):
    """
    Bloody the system lists places in district which are far off from your place.
    Hence, the pincode search, gives you places in the vicinity of your house.
    """
    base_url = 'https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByPin?pincode={0}&date={1}'
    tomorrow = _get_tomorrow()
    target_url = base_url.format(pincode, tomorrow)
    request_header.update(mandatory_request_header)
    got_response = False
    find_by_pin_response = None
    resp = None
    while not got_response:
        find_by_pin_response = requests.get(target_url, headers=request_header)
        if find_by_pin_response.status_code == 200:
            resp = find_by_pin_response.json()
            got_response = True
        else:
            print(find_by_pin_response.json())
            return False

    min_age_booking = get_min_age(beneficiary_dtls)
    minimum_slots = kwargs['min_slots']
    options = parse_calender_response(resp, minimum_slots, min_age_booking, kwargs['dose'])
    return ask_and_book(options, request_header, beneficiary_dtls, **kwargs)


def get_districts():
    """
    This function
        1. Lists all states, prompts to select one,
        2. Lists all districts in that state, prompts to select required ones, and
        3. Returns the list of districts as list(dict)
    """
    states = requests.get('https://cdn-api.co-vin.in/api/v2/admin/location/states', headers=mandatory_request_header)

    if states.status_code == 200:
        states = states.json()['states']

        refined_states = []
        for state in states:
            tmp = {'state': state['state_name']}
            refined_states.append(tmp)

        display_table(refined_states)

        state = int(input('Enter State index: '))
        state_id = states[state - 1]['state_id']

    else:
        print('Unable to fetch states')
        print(states.status_code)
        print(states.text)
        os.system("pause")
        sys.exit(1)

    districts = requests.get(f'https://cdn-api.co-vin.in/api/v2/admin/location/districts/{state_id}',
                             headers=mandatory_request_header)
    if districts.status_code == 200:
        districts = districts.json()['districts']

        refined_districts = []
        for district in districts:
            tmp = {'district': district['district_name']}
            refined_districts.append(tmp)

        display_table(refined_districts)
        reqd_districts = input('Enter comma separated index numbers of districts to monitor : ')
        districts_idx = [int(idx) - 1 for idx in reqd_districts.split(',')]
        reqd_districts = [{
            'district_id': item['district_id'],
            'district_name': item['district_name'],
            'district_alert_freq': 440 + ((2 * idx) * 110)
        } for idx, item in enumerate(districts) if idx in districts_idx]

        print(f'Selected districts: ')
        display_table(reqd_districts)
        return reqd_districts

    else:
        print('Unable to fetch districts')
        print(districts.status_code)
        print(districts.text)
        os.system("pause")
        sys.exit(1)


def get_beneficiaries(request_header):
    """
    This function
        1. Fetches all beneficiaries registered under the mobile number,
        2. Prompts user to select the applicable beneficiaries, and
        3. Returns the list of beneficiaries as list(dict)
    """
    request_header.update(mandatory_request_header)
    beneficiaries = requests.get(BENEFICIARIES_URL, headers=request_header)

    if beneficiaries.status_code == 200:
        beneficiaries = beneficiaries.json()['beneficiaries']

        refined_beneficiaries = []
        for beneficiary in beneficiaries:
            beneficiary['age'] = datetime.datetime.today().year - int(beneficiary['birth_year'])

            tmp = {
                'beneficiary_reference_id': beneficiary['beneficiary_reference_id'],
                'name': beneficiary['name'],
                'vaccine': beneficiary['vaccine'],
                'age': beneficiary['age'],
                'dose': 2 if (beneficiary['appointments'] and len(beneficiary['appointments'])>0) else 1
            }
            refined_beneficiaries.append(tmp)

        display_table(refined_beneficiaries)
        print("""
        ################# IMPORTANT NOTES #################
        # 1. While selecting beneficiaries, make sure that selected beneficiaries are all taking the same dose: either first OR second.
        #    Please do no try to club together booking for first dose for one beneficiary and second dose for another beneficiary.
        #
        # 2. While selecting beneficiaries, also make sure that beneficiaries selected for second dose are all taking the same vaccine: COVISHIELD OR COVAXIN.
        #    Please do no try to club together booking for beneficiary taking COVISHIELD with beneficiary taking COVAXIN.
        #
        # 3. If you're selecting multiple beneficiaries, make sure all are of the same age group (45+ or 18+) as defined by the govt.
        #    Please do not try to club together booking for younger and older beneficiaries.
        ###################################################
        """)
        reqd_beneficiaries = input('Enter comma separated index numbers of beneficiaries to book for : ')
        beneficiary_idx = [int(idx) - 1 for idx in reqd_beneficiaries.split(',')]
        reqd_beneficiaries = [{
            'beneficiary_reference_id': item['beneficiary_reference_id'],
            'vaccine': item['vaccine'], 'age': item['age']
        } for idx, item in enumerate(beneficiaries) if idx in beneficiary_idx]

        print(f'Selected beneficiaries: ')
        display_table(reqd_beneficiaries)
        return reqd_beneficiaries

    else:
        print('Unable to fetch beneficiaries')
        print(beneficiaries.status_code)
        print(beneficiaries.text)
        os.system("pause")


def get_min_age(beneficiary_dtls):
    """
    This function returns a min age argument, based on age of all beneficiaries
    :param beneficiary_dtls:
    :return: min_age:int
    """
    age_list = [item['age'] for item in beneficiary_dtls]
    min_age = min(age_list)
    return min_age


def generate_token_OTP(mobile):
    """
    This function generate OTP and returns a new token
    """
    data = {"mobile": mobile,
            "secret": "U2FsdGVkX1/3I5UgN1RozGJtexc1kfsaCKPadSux9LY+cVUADlIDuKn0wCN+Y8iB4ceu6gFxNQ5cCfjm1BsmRQ=="}
    print(f"Requesting OTP with mobile number {mobile}..")
    txnId = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/generateMobileOTP', json=data,
                          headers=mandatory_request_header)

    if txnId.status_code == 200:
        txnId = txnId.json()['txnId']
    else:
        print('Unable to Create OTP')
        print(txnId.text)
        os.system("pause")

    OTP = input("Enter OTP: ")
    data = {"otp": sha256(str(OTP).encode('utf-8')).hexdigest(), "txnId": txnId}
    print(f"Validating OTP..")

    token = requests.post(url='https://cdn-api.co-vin.in/api/v2/auth/validateMobileOtp', json=data,
                          headers=mandatory_request_header)
    if token.status_code == 200:
        token = token.json()['token']
    else:
        print('Unable to Validate OTP')
        print(token.text)
        os.system("pause")

    print(f'Token Generated: {token}')
    return token
