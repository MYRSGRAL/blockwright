#include <iostream>
#include <string>
#include <sstream>
#include <limits>

using namespace std;
int main() {
    setlocale(LC_ALL, "Russian");
    string text;
    string word;
    string longestWord;
    int number = 0;
    int maxNumber = 0;
    cout << "Введите текст: ";
    if (!getline(cin, text)) {
        cout << "Ошибка ввода!";
        return 1;
    }
    if (text.empty()) {
        cout << "Ошибка! Текст не должен быть пустым.";
        return 1;
    }
    istringstream iss(text);
    while (iss >> word) {
        number++;
        if (word.size() > longestWord.size()) {
            longestWord = word;
            maxNumber = number;
        }
    }
    if (number == 0) {
        cout << "Ошибка! Введите хотя бы одно слово.";
        return 1;
    }
    if (text.size() > 1000) {
        cout << "Ошибка! Текст слишком длинный.";
        return 1;
    }
    cout << "Самое длинное слово: " << longestWord << endl;
    cout << "Порядковый номер: " << maxNumber << endl;

    return 0;
}
