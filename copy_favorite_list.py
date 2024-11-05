from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import csv

# # ChromeDriverのパスを指定してServiceオブジェクトを作成
# service = Service('/home/atsushi/dev/daisuke-cafe-search/chromedriver-linux64/chromedriver')

# # ChromeOptionsを作成して新しいChromeブラウザのバイナリパスを指定
# options = Options()
# options.binary_location = '/home/atsushi/dev/daisuke-cafe-search/chrome-linux64/chrome'

# options.add_argument("user-data-dir=/home/atsushi/.config/google-chrome")  # プロファイルのパス
# options.add_argument("profile-directory=Default")  # プロファイル名（例: Default, Profile 1）

# # 追加のオプションを設定
# options.add_argument("--remote-debugging-port=9222")
# options.add_argument("--no-sandbox")
# options.add_argument("--disable-dev-shm-usage")

options = Options()
options.debugger_address = "localhost:9222"

# WebDriverを作成
# driver = webdriver.Chrome(service=service, options=options)
driver = webdriver.Chrome(options=options)

# CSVファイルを読み込む
with open('Converted_犬外席OK、散歩途中テイクアウトOK飲食店2.csv', newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        url = row['url']
        # list_name = row['list_name']
        list_name = 'backup_new'
        comment = row['comment']

        # Googleマップを開く
        driver.get(url)
        time.sleep(5)  # ページが完全に読み込まれるまで待機

        # お気に入り保存ボタンをクリック
        save_button = driver.find_element(By.XPATH, '//button[@data-value="Directions"]/parent::div/following-sibling::div/button')
        save_button.click()
        time.sleep(3)

        # リスト名を選択
        list_input = driver.find_element(By.XPATH, f'//div[text()="{list_name}"]/ancestor::div[@jsaction][1]')
        # list_input.click()
        list_input.send_keys(list_name)
        list_input.send_keys(Keys.RETURN)
        time.sleep(3)

        if not comment:
            continue
        
        place_list_button = driver.find_element(By.XPATH, '//button[@aria-label="Show place lists details"]')
        place_list_button.click()
        time.sleep(3)

        add_note_button = driver.find_element(By.XPATH, f'//button[@aria-label="Add note in {list_name}"]')
        add_note_button.click()
        time.sleep(3)


        # # コメントを入力
        comment_input = driver.find_element(By.XPATH, '//h1[text()="Add note"]/following::textarea[1]')
        comment_input.send_keys(comment)
        # comment_input.send_keys(Keys.RETURN)
        time.sleep(3)

        done_btn = driver.find_element(By.XPATH, '//button[text()="Done"]')
        done_btn.click()
        time.sleep(3)


# ブラウザを閉じる
driver.quit()

