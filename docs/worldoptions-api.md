# World Options SOAP web service - contract notes

The merchant's account uses World Options' **SOAP web service** (WCF, `BasicHttpBinding`,
SOAP 1.1, document/literal), not the REST Ecommerce API. Public base:
`http://service.worldoptions.co.uk` (the WSDLs advertise an internal host in their
`soap:address`/`schemaLocation`, but the public host serves the WSDL, the XSDs at
`?xsd=xsdN`, and accepts the POSTs). All three services live at the same host.

## Auth (every request) - `wsAuthenticationDetail`
`{Key, MeterNumber, Password, PluginCode, SubUserKey, WebLeadCompanyName, WebLeadPostalCode}`.
The merchant has a **Meter Number**; `PluginCode` is an enum whose `Web_Service` value is
the direct-integration one. `Key`/`Password` may also be required - collected in Settings.

## 1. Quote - `RateService.svc` / `GetAllServicesAndRates`
SOAPAction `http://tempuri.org/IRateService/GetAllServicesAndRates`.
Request `RateServiceRequest`:
- `AuthenticationDetail`
- `RecipientDetails` (`wsDeliveryDetail`): `{DeliveryCity, DeliveryCountryCode, DeliveryPostCode, DeliveryState, IsResidential}`
- `SenderDetails` (`wsCollectionDetail`): `{CollectionCity, CollectionCountryCode, CollectionCountryState, CollectionPostCode}`
- `ShippingDetails` (`wsShippingDetails`): `PackageDetails[{Breadth, CustomValue, Height, ItemNumber, Length, Weight}]`,
  `ServiceName` (`wsServiceCompanyTypes`, `ALL` = every carrier), `ServiceTypeName` (`wsServiceTypes`, `ALL`), + option flags.
Reply `RateServiceReply`: `{Message, NotificationtType (SUCCESS|FAILED|WARNING),
wsRateService: [wsAvailableServicesAndRates]}`. Each option:
`{wsServiceCode, wsServiceTypeCode, wsServiceTypeName, wsServiceTypeCategory, wsPackageTypeCode,
wsPickupDateTime, wsDeliveryDateTime, wsQuoteDetails{TotalNetCharge, ServiceType, ServiceTypeName, serviceId, ...many surcharges}}`.
**Price = `wsQuoteDetails/TotalNetCharge`.** The option's `wsServiceTypeCode` + `wsPackageTypeCode`
feed straight into the booking.

## 2. Book - `ShipmentService.svc` / `DoShipment`
SOAPAction `http://tempuri.org/IShipmentService/DoShipment`. **This books and charges.**
Request `ShipmentBookingRequest`:
- `AuthenticationDetail`
- `BillingDetail` (`wsBillingDetail`, optional): collection scheduling, payors, notifications.
- `RecipientsDetails` (`wsRecipient`): `{Address1..3, City, Company, Country_Code, Email, Fax, Name, Phone, PhoneDialCode, Postalcode, Residential, State_Code}`
- `SendersDetails` (`wsSender`): `{Address1..3, City, Company, CountryCode, Email, Name, Phone, PhoneDialCode, PostalCode, State}`
- `ShippingDetail` (`wsShippingDetail`): `PackageDetails[{Breadth, CustomValue, Height, ItemNumber, Length, Wt}]` (note **Wt**, not Weight),
  `ServiceType` (carrier, `wsServiceCompanyTypes`), `ServiceTypeCode` (service, `wsServiceTypes`),
  `PackageTypeCode` (`wsPackageTypes` - use the quote's `wsPackageTypeCode`), `Currency`, `CustomerReference`, `CollectionType` (`Regular`).
Reply `ShipmentBookingReply`: `{MasterTrackingNo, Labels: [ShippingLabel{Image (base64), ImageLength, IsThermalPrint, LabelType, LabelURL}],
CollectionDateNumber, Message, Warning, NotificationtType}`.

## 3. Cancel - `VoidService.svc` / `VoidShipment`
Request `VoidRequest{AuthenticationDetail, TrackingNumber}` -> `VoidReply{Message, NotificationtType}`.

## Enums (from xsd6)
- **Carriers** `wsServiceCompanyTypes`: ALL, DHL, FEDEX, UPS, TNT, Palletways, YODEL, DHLPARCEL, DXEXPRESS, HERMES, DSV, EXFreight, GLOBALTRANZ, CITYSPRINT, EVRISEND, EVRICORPORATE, TUFFNELLS, ROYALMAIL, DPD.
- **Services** `wsServiceTypes` (146): UPS_Express, UPS_Standard, DHL_Worldwide_Express, RoyalMail_*, DPD_*, etc.
- **Package types** `wsPackageTypes`: RoyalMail_Parcel, DPD_Parcel, Evri_Parcel, UPS_My_Packaging, Fedex_Your_Packaging, DHL_NonDocument, ...
- **Currency** `CurrencyTypes`: GBP, USD, EUR, CAD, AUD, NZD, SGD.

## Build notes
- WCF DataContractSerializer needs each type's child elements in **alphabetical order** and in the
  **containing type's namespace** (elementFormDefault=qualified). Namespaces:
  tempuri (`http://tempuri.org/`), WOWebServices (`.../WOWebServices`), Model (`.../WOWebServices.Model`),
  wsRateShipmentDetails, wsShippingDetails, WOModel.GlobalTypes, wsGlobalTypes, ShippingLabel.
- Quote package weight field is `Weight`; booking package weight field is `Wt`.
- `NotificationtType == "FAILED"` (their spelling) means the call was rejected; `Message` carries why.
- Hand-rolled envelopes (no zeep) so the module stays async + dependency-free; the XSD imports point at
  an internal host zeep couldn't resolve anyway. Confine everything to `worldoptions.py`.

## Booking hard requirements (learned from live ValidationFault probing)
- BOTH sender and recipient need Phone AND Email or DoShipment rejects with an
  EnterpriseLibrary ValidationFault ("Please provide phone for collection", ...).
  The fault's reasons live in the fault DETAIL (ValidationDetail/Message), not the
  faultstring - _parse extracts them. The app preflights: origin must carry both
  (settings error otherwise); a missing customer phone/email falls back to the
  shop's with a warning note.
- Full capability envelope (customs AdditionalShipmentDetail first + multi-box +
  Insurance + DeliverySignatureType + collection window) verified against the
  live service: deserializes + passes validation, fails only on dummy credentials
  ("Customer authentication failed").

## Capabilities in the app (2026-08-11)
- Customs: AdditionalShipmentDetail (EORI/goods HTS lines/invoice Help_Me_Generate/
  export reason/duties payor/trade term/receiver tax id), required for non-GB.
- Multi-parcel: boxes[] end to end (cap 15), declared value spread per box.
- Insurance: quote + booking Insurance amount.
- Drop-off: IsCollectionDropoffRequired on quotes when the merchant's collection
  arrangement is drop-off; nearest wsCollectionDropOffShop booked as
  CollectionDropOffInfo and shown in the UI.
- Signatures: per-carrier DeliverySignatureType (SIGNATURE_OPTIONS).
- Quote breakdown: non-zero wsQuoteDetail charges parsed + shown per option.
