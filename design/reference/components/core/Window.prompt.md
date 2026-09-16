Окно с заголовком — используй как оболочку экрана игры, окна свойств и любого диалога.

```jsx
<Window title="Свойства: учётная запись" titleCn="我的" icon="assets/icons/desktop-person.svg"
  status={<StatusBar items={["Сезон не начался", "Вид: Луна-Аква"]} />}>
  <Tabs items={[{id:"view",label:"Вид"},{id:"help",label:"Помощь"}]} value="view" onChange={setTab} />
</Window>
```

Заголовок — это имя окна, не название действия. Строку состояния держи фактической: что знает сервер, ничего больше.
